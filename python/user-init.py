#!/usr/bin/env python3

# assume cluster-map has the following format
# clusters:
# - az: AZ1
#   cluster: cluster1
#   # will simply use filename as configmap's key
#   conf: /etc/ceph/az1-cluster1-ceph.conf
#   admin: admin
#   pools:
#   - name: volumes
#     size: 3
#     num: 128
#     crush_rule: rule
#   users:
#   - user: user1
#     secret_uuid: uuid1
#     keyring: /etc/ceph/user1.keyring
#   - user: user2
#     secret_uuid: uuid2
# - az: az2
#   cluster: cluster2
#   conf: /etc/ceph/az2-cluseter1-ceph.conf
#   admin: admin
#   users:
#   - user: user1
#   - user: user2

# ! always bootstrap with a user got admin privilege

import logging
import subprocess
import argparse
import yaml
import shlex
from kubernetes import client, config
import kubernetes
import json


logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)
CLIENT_KEYRING_PATH_TEMPL = """
[client.%s]
keyring = %s
"""


try:
    import rados
except Exception:
    LOG.warning('rados not found')


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--config', type=str, help='path to cluster map file'
    )
    parser.add_argument(
        '--namespace', type=str, help='namespace save configmap to',
        default='openstack'
    )
    parser.add_argument(
        '--configmap', type=str, help='name of configmap',
        default='ceph-confs'
    )
    parser.add_argument(
        '--libvirt_secret', type=str, help='name of libvirt serets',
        default='libvirt-secrets'
    )
    return parser.parse_args()


def exec_shell_command(command):
    LOG.info('shell executed: %s' % command)
    process = subprocess.Popen(shlex.split(command),
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr


def create_ceph_user(conf, admin, user):

    tmpl_get_user = "ceph -c %s --id %s auth get client.%s"
    tmpl_create_auth = 'ceph -c %s --id %s auth get-or-create client.%s mon "profile rbd" osd "profile rbd"'
    tmpl_reset_cap = 'ceph -c %s --id %s auth caps client.%s mon "profile rbd" osd "profile rbd"'

    code, stdout, stderr = exec_shell_command(
        tmpl_get_user % (conf, admin, user))

    if code == 0:
        # user exists, so update its caps instead
        code, _, _ = exec_shell_command(tmpl_reset_cap % (conf, admin, user))
        if code == 0:
            code, stdout, _ = exec_shell_command(tmpl_get_user % (conf, admin, user))
            if code == 0:
                # use default locale on purpose
                return stdout.decode()
            else:
                raise Exception("get user privilege failed")
        else:
            raise Exception("reset user privilege failed")
    else:
        code, stdout, _ = exec_shell_command(tmpl_create_auth % (conf, admin, user))
        if code != 0:
            raise Exception('create user failed')
        # use default locale on purpose
        return stdout.decode()


def get_ceph_auth_key(conf, admin, user):
    tmpl_get_auth_key = "ceph -c %s --id %s auth get-key client.%s"
    code, stdout, stderr = exec_shell_command(tmpl_get_auth_key % (conf, admin, user))
    if code == 0:
        return stdout.decode()
    else:
        raise Exception("get user auth key failed: %s" % stderr)


def save_configmap(namespace, name, data):
    try:
        config.load_kube_config()
    except Exception as e:
        config.load_incluster_config()
    v1 = client.CoreV1Api()
    cm = {
        "metadata": {
            "name": name
        },
        'data': data
    }
    try:
        v1.read_namespaced_config_map(name, namespace)
        v1.replace_namespaced_config_map(name, namespace, cm)
    except kubernetes.client.rest.ApiException:
        v1.create_namespaced_config_map(
            namespace=namespace, body=cm)


def get_keyring_name(az, cluster, user):

    base = "ceph.client.%s.keyring" % user

    if az:
        base = base + "-%s" % az
    if cluster:
        base = base + "-%s" % cluster
    return base


def ensure_pools(conf, user, pool):

    r = None
    try:
        r = rados.Rados(rados_id=user, conffile=conf)
        r.connect()

        if not r.pool_exists(pool['name']):
            r.create_pool(pool['name'])
        ioctx = r.open_ioctx(pool['name'])
        app = pool.get('application', 'rbd')

        # enable application on pool
        ioctx.application_enable(app, True)

        # set other values
        ceph_pool_set_tmpl = 'ceph -c %%s --id %%s osd pool set %%s %s %%s'
        ceph_pool_get_tmpl = 'ceph -c %%s --id %%s osd pool get %%s %s'
        size = int(pool.get('size', -1))
        if size > 0:
            set_size_tmpl = ceph_pool_set_tmpl % 'size'
            exec_shell_command(set_size_tmpl % (conf, user, pool['name'], size))

        pg = int(pool.get('num', -1))
        pg_get_tmpl = ceph_pool_get_tmpl % 'pg_num'
        code, ret, stderr = exec_shell_command(pg_get_tmpl % (conf, user, pool['name']))
        pg_num_cur = int(ret.decode().split(' ')[-1])
        if pg > pg_num_cur:
            pg_tmpl = ceph_pool_set_tmpl % 'pg_num'
            pgp_tmpl = ceph_pool_set_tmpl % 'pgp_num'
            exec_shell_command(pg_tmpl % (conf, user, pool['name'], pg))
            exec_shell_command(pgp_tmpl % (conf, user, pool['name'], pg))
        elif pg < pg_num_cur:
            LOG.warning('pg num should be greater than %s for %s' % (pg_num_cur, pool['name']))

        crush_rule = pool.get('crush_rule', None)
        if crush_rule:
            crush_rule_set = ceph_pool_set_tmpl % "crush_rule"
            exec_shell_command(crush_rule_set % (conf, user, pool['name'], crush_rule))

    except Exception as e:
        LOG.exception(e)
    finally:
        try:
            if r:
                r.shutdown()
        except Exception as e:
            LOG.exception(e)

    return


def main():
    args = parse_args()
    cluster_map_path = args.config

    with open(cluster_map_path, 'r') as f:
        cluster_map = yaml.load(f)

    # data to be stored in configmap
    data = {}
    secrets = {}

    # create required users using given configuration file
    for c in cluster_map.get('clusters', []):
        try:
            az = c.get('az', '')
            cluster = c.get('cluster', '')
            conf_path = c.get('conf', 'ceph.conf')
            with open(conf_path, 'r') as f:
                content = '\n'.join(f.readlines())
            admin_name = c.get('admin', 'admin')
            users = c.get('users', [])
            for u in users:
                name = u['user']
                keyring_path = u.get('keyring', get_keyring_name(az, cluster, name))
                try:
                    user_keyring = create_ceph_user(conf_path, admin_name, name)
                    if '/' in keyring_path:
                        content = content + CLIENT_KEYRING_PATH_TEMPL % (name, keyring_path)
                    else:
                        # keyring path has to be absolute to avoid problems
                        content = content + CLIENT_KEYRING_PATH_TEMPL % (name, '/etc/ceph/' + keyring_path)
                    data[keyring_path.split('/')[-1]] = user_keyring
                    if u.get('secret_uuid', None):
                        secrets[u['secret_uuid']] = get_ceph_auth_key(conf_path, admin_name, name)
                except Exception as e:
                    LOG.error("create user %s failed with %s" % (u, e))
            # pick the current filename
            data[conf_path.split('/')[-1]] = content

            pools = c.get('pools', [])
            for pool in pools:
                ensure_pools(conf_path, admin_name, pool)

        except Exception as e:
            LOG.error(e)
            continue

    # create configmap
    save_configmap(args.namespace, args.configmap, data)

    save_configmap(args.namespace, args.libvirt_secret, {"secrets": json.dumps(secrets)})


if __name__ == '__main__':
    main()

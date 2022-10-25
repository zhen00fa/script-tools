#!/usr/bin/env python

import logging
import subprocess
from kubernetes import client, config
import json
import base64
from oslo_config import cfg
import shlex
import socket


logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


def init():
    register_opts(cfg.CONF)


def register_opts(conf):
    conf.register_cli_opt(
        cfg.StrOpt(
            'output',
            default='/tmp/pod-share/nova-compute-custom.conf'
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'namespace',
            default='openstack'
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'hostname-prefix',
            default='nova-compute-'
        )
    )
    # init
    conf(
        project='nova-compute-init-pre'
    )


# def exec_shell_command(command):
#     LOG.info('shell executed: %s' % command)
#     process = subprocess.Popen(shlex.split(command),
#                                stdout=subprocess.PIPE,
#                                stderr=subprocess.PIPE,
#                                shell=True)
#     stdout, stderr = process.communicate()
#     if process.returncode == 0:
#         return stdout.decode()
#     else:
#         raise Exception("Execute command failed" % stderr)


def get_hostname():
    return socket.gethostname()


def parse_config_secret(hostname, namespace):
    """
    解析etc文件
    """
    config.load_kube_config()
    v1 = client.CoreV1Api()
    secret = v1.read_namespaced_secret(hostname, namespace).data
    return secret


def generate_config_file(secrets):
    """
    根据hostname查找对应的secret并解析成oslo_config格式的配置文件
    文件路径：/tmp/pod-share/nova-compute-custom.conf
    """
    sec = base64.b64decode(secrets.get('nova-compute.conf'))
    save_files(sec.decode("utf-8"), cfg.CONF.output, 'w')


def save_files(file, path, mode='w'):
    with open(path, mode) as f:
        f.write(file)


def generate_env(secrets):
    """
    将nova-compute-init-env.conf定义的内容生成环境变量列表
    """
    tmpl_export_env = "export %s=%s" + '\n'
    envs = base64.b64decode(secrets.get('nova-compute-init-env.conf'))
    listed_envs = json.loads(envs.decode("utf-8"))
    analyze_data(listed_envs, tmpl_export_env)


def analyze_data(data, tmpl):
    for k, v in data.items():
        if isinstance(v, dict):
            analyze_data(v, tmpl)
        else:
            # os.system(tmpl % (str(k).upper(), v))
            # exec_shell_command(tmpl % (str(k).upper(), v))
            save_files(tmpl % (str(k).upper(), v), '/tmp/cmp_env', 'a')


def main():
    init()
    hostname = cfg.CONF.hostname_prefix + get_hostname()
    secrets = parse_config_secret(hostname, cfg.CONF.namespace)
    generate_config_file(secrets)
    generate_env(secrets)


if __name__ == "__main__":
    main()



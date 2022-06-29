#!/usr/bin/env python3

import logging
from logging.handlers import RotatingFileHandler
import os
import time
import sys
from concurrent.futures import ThreadPoolExecutor

from oslo_config import cfg

from keystoneauth1 import loading, session
from novaclient import client as novac

log_name = '/tmp/lz/testlog'
logging.basicConfig(filename=log_name, filemode='a', level=logging.INFO)
LOG = logging.getLogger(__name__)
handler = RotatingFileHandler(log_name, maxBytes=5*1024*1024*1024, backupCount=1)
LOG.addHandler(handler)

global failed_count
failed_count = 0


def init():
    register_opts(cfg.CONF)


def register_opts(conf):
    conf.register_cli_opt(
        cfg.ListOpt(
            'instance-id'
        )
    )
    conf.register_cli_opt(
        cfg.IntOpt(
            'workers',
            default='1'
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'image-id'
        )
    )
    conf.register_cli_opt(
        cfg.IntOpt(
            'times',
            default='5'
        )
    )
    # init
    conf(
        project='test-rebuild'
    )


AUTH_URL = os.getenv('OS_AUTH_URL')
USERNAME = os.getenv('OS_USERNAME')
PASSWORD = os.getenv('OS_PASSWORD')
PROJECT_NAME = os.getenv('OS_PROJECT_NAME')
DOMAIN_NAME = os.getenv('OS_DEFAULT_DOMAIN')


tcp_established = "ESTABLISHED"


def get_nova_client():
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=AUTH_URL,
                                    username=USERNAME,
                                    password=PASSWORD,
                                    project_name=PROJECT_NAME,
                                    user_domain_name=DOMAIN_NAME,
                                    project_domain_name=DOMAIN_NAME)
    sess = session.Session(auth=auth)
    return novac.Client('2.11', session=sess, endpoint_type='internal')


def get_server_obj(server_id, client):
    vm_obj = client.servers.get(server_id)
    return vm_obj


def rebuild_instance(server_id, image_id, client):
    try:
        vm_obj = get_server_obj(server_id, client)
    except Exception as ex:
        message = getattr(ex, "message", str(ex))
        print("Got error: %s" % message)
    if vm_obj.status == "ACTIVE":
        try:
            vm_obj.rebuild(image=image_id)
            time.sleep(10)
        except Exception as rebex:
            rebuild_fail_mesg = getattr(rebex, "message", str(rebex))
            failed_count += 1
            sys.stderr.write("rebuild server %s rebuild failed cause %s, total failed %s times"
                             % (server_id, rebuild_fail_mesg, failed_count))
    elif vm_obj.status == "REBUILD":
        time.sleep(10)
        rebuild_instance(server_id, client)
    elif vm_obj.status == "ERROR":
        failed_count += 1
        logging.ERROR(vm_obj.fault)
        sys.stderr.write("Server %s rebuild failed cause status is in %s, total failed %s times"
                         % (server_id, vm_obj.status, failed_count))


# def check_server_status(vm_obj):
#     return vm_obj.status


# def get_image_uuid(vm_obj, client):
#     try:
#          client.volumes.get_server_volumes(vm_obj.id)


def main():
    init()
    nova_client = get_nova_client()
    for i in range(cfg.CONF.times):
        Pool = ThreadPoolExecutor(max_workers=cfg.CONF.workers)
        for uuid in cfg.CONF.instance_id:
            Pool.submit(rebuild_instance, uuid, cfg.CONF.image_id, nova_client)
        Pool.shutdown(wait=True)


if __name__ == "__main__":
    main()


# python3 rebuildInstanceTest.py --instance-id 03a33f72-ae81-4871-abb1-3222e1d9cce3 --workers 1 --image-id 03b3ff5f-9e07-42c6-820e-6970ac738579 --times 2

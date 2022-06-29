#!/usr/bin/env python

import sys
import shlex
import socket
from cinder import version
from cinder.volume import rpcapi
from cinder.volume import configuration
from oslo_utils import importutils
from cinder import rpc

from cinder import objects
objects.register_all()
from os_brick.initiator import connector
from cinder import context
from cinder.cmd.volume import host_opt
from cinder.volume.drivers.rbd import RADOSClient
from oslo_config import cfg
from oslo_log import log
from oslo_privsep import priv_context
from cinder import volume as cinder_volume


LOG = log.getLogger(__name__)


def init_app():
    """initialize application"""

    # objects.register_all()
    cfg.CONF(
        sys.argv[1:],
        project='cinder',
        version=version.version_string()
    )

    # choose the first in backend list
    backend = cfg.CONF.enabled_backends[0]
    cfg.CONF.register_opt(
        host_opt,
        backend
    )

    # get backend host
    backend_host = getattr(
        cfg.CONF,
        backend
    ).backend_host

    if not backend_host:
        backend_host = socket.gethostname()

    # form a host
    host = "%s@%s" % (
        backend_host,
        backend
    )

    rpc.init(cfg.CONF)

    return (
        backend, host, None
    )


def register_opts():
    cfg.CONF.register_cli_opt(
        cfg.StrOpt(
            'volume-id'
        )
    )


if __name__ == '__main__':

    # register a new cli opt
    register_opts()
    init_app()

    ctx = context.get_admin_context()
    volume_obj = objects.Volume.get_by_id(
        ctx, cfg.CONF.volume_id
    )

    volume_api = cinder_volume.API()
    rpc_api = rpcapi.VolumeAPI()
    for i in range(10):
        try:
            # volumes = volume_api.get_all(ctx, filters={"all_tenants": True, "status": "creating"})
            # volume_objs = objects.VolumeList.get_all(
            #     ctx, filters={"host": "cinder-volume-worker@FC_std_fnw#JT-FHX-NW-STR01", "status": "creating"}
            #
            # )
            # print(len(volume_objs))
            cctx = rpc_api._get_cctxt(volume_obj.service_topic_queue)
            cctx.call(ctx, "sjt_test_api")
        except Exception as e:
            print(e)



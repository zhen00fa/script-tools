import sys
import socket
from cinder import version
from oslo_config import cfg
from cinder import context as cinder_context
from cinder import objects
objects.register_all()
from cinder.cmd.volume import host_opt
from cinder import rpc
from cinder.scheduler.host_manager import HostManager
from cinder.common import constants
from cinder.volume import API
from cinder import volume as cinder_volume
CONF = cfg.CONF


def init_app():
    """initialize application"""

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


def main():
    ctx = cinder_context.get_admin_context()
    elevated = ctx.elevated()
    hm = HostManager()
    backends = hm.get_all_backend_states(elevated)
    print(len(list(backends)))
    topic = constants.VOLUME_TOPIC
    volume_services = objects.ServiceList.get_all(elevated,
                                                  {'topic': topic,
                                                   'disabled': False,
                                                   'frozen': False})
    for vs in volume_services.objects:
        print("%(host) %(isup)", {'host': vs.host, 'isup': vs.is_up})
    print(len(volume_services))
    vol_api = API()
    volumes = vol_api.get_all(ctx, filters={"all_tenants": True, "status": "in-use"})
    print(len(volumes))


if __name__ == "__main__":
    init_app()
    main()

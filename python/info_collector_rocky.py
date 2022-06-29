from cinder import objects
from cinder import context
from oslo_config import cfg
import oslo_messaging
import sys
from cinder import version
from cinder.cmd.volume import host_opt
from oslo_utils import importutils


def init_app():
    """initialize application"""

    objects.register_all()
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
    backend_host = 'cinder-volume-worker'
    # backend_host = getattr(
    #     cfg.CONF,
    #     backend
    # ).backend_host#

    if not backend_host:
        print("please add a backend host")
        sys.exit(1)

    # form a host
    host = "%s@%s" % (
        backend_host,
        backend
    )

    # import and initialize db driver module V版本 去掉注释
    #db_driver = importutils.import_module(cfg.CONF.db_driver)
    #db_driver.dispose_engine()

    #return (
    #    backend, host, db_driver
    #)
    # import and initialize db driver module R版本
    # db_driver = importutils.import_module(cfg.CONF.db_driver)
    # db_driver.dispose_engine()
    #
    # return (
    #     backend, host, db_driver
    # )

def register_opts():
    pass


class InfoEndpoint(object):

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        if event_type.startswith('audit'):
            return
        print(publisher_id, event_type, payload)


# run script with
# python3 info_collector.py --config-dir /etc/cinder --config-dir /etc/cinder/conf # noqa
if __name__ == '__main__':
    # register a new cli opt
    register_opts()
    init_app()

    # demo usage of VolumeList
    ctx = context.get_admin_context()

    # start notification listener
    transport = oslo_messaging.get_notification_transport(cfg.CONF)
    targets = [
        oslo_messaging.Target(topic='notifications'),
    ]
    endpoints = [
        InfoEndpoint()
    ]
    server = oslo_messaging.get_notification_listener(transport, targets,
                                                      endpoints)
    server.start()
    server.wait()

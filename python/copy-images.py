#!/usr/bin/env python

import argparse
import os
from os import environ
from keystoneauth1 import session, loading
from oslo_config import cfg
from oslo_log import log
from oslo_privsep import priv_context
from cinderclient.v3 import client as cinderclient
from glanceclient.v2 import client as glanceclient

LOG = log.getLogger(__name__)

AUTH_URL = os.getenv('OS_AUTH_URL')
USERNAME = os.getenv('OS_USERNAME')
PASSWORD = os.getenv('OS_PASSWORD')
PROJECT_NAME = os.getenv('OS_PROJECT_NAME')
DOMAIN_NAME = os.getenv('OS_DEFAULT_DOMAIN')


def register_opts():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--auth-url', dest='auth_url',
        default=environ.get('OS_AUTH_URL', None)
    )
    parser.add_argument(
        '--endpoint-type', dest='endpoint_type',
        default=environ.get('OS_INTERFACE', 'admin')
    )
    parser.add_argument(
        '--username', dest='username',
        default=environ.get('OS_USERNAME', None)
    )
    parser.add_argument(
        '--region-name', dest='region_name',
        default=environ.get('OS_REGION_NAME', None)
    )
    parser.add_argument(
        '--password', dest='password',
        default=environ.get('OS_PASSWORD', None)
    )
    parser.add_argument(
        '--user-domain-name', dest='user_domain_name',
        default=environ.get('OS_USER_DOMAIN_NAME', None)
    )
    parser.add_argument(
        '--project-name', dest='project_name',
        default=environ.get('OS_PROJECT_NAME', None)
    )
    parser.add_argument(
        '--project-domain-name', dest='project_domain_name',
        default=environ.get('OS_PROJECT_DOMAIN_NAME', None)
    )
    parser.add_argument(
        '--method', dest='method',
        default='copy-image'
    )
    parser.add_argument(
        '--stores', dest='stores',
        default=[]
    )
    parser.add_argument(
        '--all-stores-must-succeed', dest='all_stores_must_succeed',
        default=False
    )
    parser.add_argument(
        '--all-stores', dest='all_stores',
        default=False
    )
    parser.add_argument(
        '--src-store', dest='src_store'
    )
    return parser.parse_args()


class ClientProxy(object):

    def __init__(self, conf):
        self.interface = conf.endpoint_type
        self.project_domain_name = 'Default'
        self.username_domain_name = "Default"
        self.username = conf.username
        self.password = conf.password
        self.project_name = conf.project_name
        self.auth_url = conf.auth_url
        self.region_name = conf.region_name
        self.init_session()
        self._volumes = cinderclient.Client(
            self.username, self.password, self.project_name,
            auth_url=self.auth_url,
            region_name=self.region_name,
            insecure=True,
            endpoint_type=self.interface
        )
        self._images = glanceclient.Client(
            session=self.session, region_name=self.region_name,
            interface=self.interface
        )

    def init_session(self):
        loader = loading.get_plugin_loader('password')
        auth = loader.load_from_options(**dict(
            auth_url=self.auth_url,
            username=self.username,
            password=self.password,
            user_domain_name=self.username_domain_name,
            project_name=self.project_name,
            project_domain_name=self.project_domain_name
        ))
        self.session = session.Session(auth=auth, verify=False)

    @property
    def volumes(self):
       return self._volumes.volumes

    @property
    def images(self):
        return self._images.images

    @property
    def image_tags(self):
        return self._images.image_tags


def get_images(client_proxy):
    """
    run and update volume metadata before image deleted
    :param client_proxy: proxy to openstack client
    :return:
    """
    images = {}

    for img in client_proxy.images.list():
        tags = img.tags
        metadata = {}
        for meta_name in REQUIRED_PROPERTIES:
            if hasattr(img, meta_name):
                metadata[meta_name] = getattr(img, meta_name, None)
        images[img.id] = {
            "name": img.name,
            "tags": tags,
            "metadata": metadata
        }
    return images


def import_images(client_proxy):
    pass


def delete_images(client_proxy):
    pass


if __name__ == '__main__':
    conf = register_opts()
    proxy = ClientProxy(conf)

    pass


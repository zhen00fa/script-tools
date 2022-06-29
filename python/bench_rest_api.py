#!/usr/bin/env python

from __future__ import print_function
from os import environ
import cProfile
import pstats
import json
import time

from oslo_config import cfg
from cinderclient.v3 import client as cinderclient
from keystoneauth1 import session, loading
from novaclient import client as nova_client
from novaclient import api_versions
from novaclient import exceptions as novaclient_exceptions

import logging
import pdb

# this script is used to determine if there is still enough
# resource a given flavor

logging.basicConfig(
    filename='/tmp/output.log',
    format='%(asctime)s %(name)s: %(levelname)s %(message)s',
    level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')

LOG = logging.getLogger(__name__)
CONSUMER_GENERATION_VERSION = '1.28'
__results = {}


class PlacementClient(object):
    def __init__(self, session):
        self.session = session
        self.prefix = session.get_endpoint(service_type='placement', interface=cfg.CONF.endpoint_type)

    def get_allocations(self, consumer):
        resp = self.session.get(
            "%s/allocations/%s" % (self.prefix, consumer),
        )
        return resp.json()


class ClientProxy(object):

    def __init__(self, conf, endpoint_override=None):
        self.session = None
        self.endpoint_override = endpoint_override
        self.project_domain_name = conf.project_domain_name
        self.username_domain_name = conf.user_domain_name
        self.username = conf.username
        self.password = conf.password
        self.project_name = conf.project_name
        self.auth_url = conf.auth_url
        self.region_name = conf.region_name
        self.endpoint_type = conf.endpoint_type
        self.init_session()
        self._volumes = cinderclient.Client(
            self.username, self.password, self.project_name,
            auth_url=self.auth_url,
            region_name=self.region_name,
            endpoint_override=self.endpoint_override,
            insecure=True
        )
        self._compute = nova_client.Client(
            api_versions.get_api_version('2.53'),
            session=self.session,
            endpoint_type=self.endpoint_type,
            endpoint_override=self.endpoint_override,
            region_name=self.region_name)
        self._placement = PlacementClient(self.session)

    def init_session(self):
        loader = loading.get_plugin_loader('v3password')
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
    def servers(self):
        return self._compute.servers

    @property
    def services(self):
        return self._compute.services

    @property
    def hypervisors(self):
        return self._compute.hypervisors

    @property
    def placement(self):
        return self._placement

    @property
    def flavors(self):
        return self._compute.flavors


def register_opts(conf):
    conf.register_cli_opt(
        cfg.StrOpt(
            "auth-url",
            default=environ.get('OS_AUTH_URL', None)
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            "username",
            default=environ.get('OS_USERNAME', None)
        )

    )
    conf.register_cli_opt(
        cfg.StrOpt(
            "password",
            default=environ.get('OS_PASSWORD', None)
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            "user-domain-name",
            default=environ.get('OS_USER_DOMAIN_NAME', None)

        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'project-name',
            default=environ.get('OS_PROJECT_NAME', None)
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'project-domain-name',
            default=environ.get('OS_PROJECT_DOMAIN_NAME', None)
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'region-name',
            default=environ.get('OS_REGION_NAME', None)
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'endpoint-type',
            default=environ.get('OS_ENDPOINT_TYPE', 'public')
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'alternative-endpoint',
            default=None,
            required=False,
            help="another endpoint used to test with the from of http://ip:port/v2"
        )
    )
    conf.register_cli_opt(
        cfg.IntOpt(
            'limit',
            default=20
        )
    )
    conf.register_cli_opt(
        cfg.IntOpt(
            'times',
            default=1
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'output',
            default='/tmp/results.%s' % int(time.time())
        )
    )
    conf.register_cli_opt(
        cfg.IntOpt(
            'step-size',
            default=10
        )
    )

    # init
    conf(
        project='perf-server-list'
    )


def cprofile_decorator(f):
    def wrapped(times, limit, *args):
        pr = cProfile.Profile()
        pr.enable()
        f(times, limit, *args)
        pr.disable()

        # pstats.Stats(pr).sort_stats(SortKey.CUMULATIVE).print_stats()
        # print('total times %50s: %s running %s times with batch size %s' % (
        # f.__name__, pstats.Stats(pr).total_tt, times, limit))

        if f.__name__ in __results:
            if limit in __results[f.__name__]:
                last = __results[f.__name__][limit][-1]
                __results[f.__name__][limit].append(
                    (last[0] + 1, pstats.Stats(pr).total_tt))
            else:
                __results[f.__name__][limit] = [(1, pstats.Stats(pr).total_tt)]
        else:
            __results[f.__name__] = {limit: [(1, pstats.Stats(pr).total_tt)]}

    return wrapped


def init():
    register_opts(cfg.CONF)


@cprofile_decorator
def test_rest_all_tenants_volume(times, limit, client):
    client.volumes.list(
        search_opts={
            "all_tenants": True
        },
        limit=limit
    )


@cprofile_decorator
def test_rest_all_tenants_volume_with_detail(times, limit, client):
    client.volumes.list(
        detailed=True,
        search_opts={
            "all_tenants": True
        },
        limit=limit
    )


@cprofile_decorator
def test_rest_all_tenants(times, limit, client):
    client.servers.list(
        search_opts={
            "all_tenants": True
        },
        limit=limit
    )


@cprofile_decorator
def test_rest_all_tenants_new(times, limit, client):
    client.servers.list(
        search_opts={
            "all_tenants": True
        },
        limit=limit
    )


@cprofile_decorator
def test_rest_active_all_tenants(times, limit, client):
    client.servers.list(
        search_opts={
            "all_tenants": True,
            "status": "active"
        },
        limit=limit
    )


@cprofile_decorator
def test_rest_active_all_tenants_new(times, limit, client):
    client.servers.list(
        search_opts={
            "all_tenants": True,
            "status": "active"
        },
        limit=limit
    )


def output():
    result = __results
    with open(cfg.CONF.output, "w") as f:
        f.write(json.dumps(result))


def main():
    # init everything
    init()
    client = ClientProxy(cfg.CONF)

    # test rest request to another endpoint
    new_client = None
    if cfg.CONF.alternative_endpoint:
        new_client = ClientProxy(cfg.CONF, endpoint_override=cfg.CONF.alternative_endpoint)

    # start benchmarking
    l = cfg.CONF.step_size
    while l <= cfg.CONF.limit:
        t = 1
        while t <= cfg.CONF.times:
            test_rest_all_tenants_volume(1, l, client)
            test_rest_all_tenants_volume_with_detail(1, l, client)
            # test_rest_active_all_tenants(1, l, client)
            if new_client:
                test_rest_active_all_tenants_new(1, l, new_client)
                # test_rest_all_tenants_new(1, l, new_client)
            t += 1
        l += cfg.CONF.step_size
    output()


if __name__ == '__main__':
    main()


# python bench_rest_api.py --limit 60  --step-size 10 --times 3  --output /tmp/results-test --endpoint-type internal --alternative-endpoint "100.101.89.208:8776/v3"
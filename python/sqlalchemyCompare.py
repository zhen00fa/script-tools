#!/usr/bin/env python
import cProfile
from pstats import SortKey
import pstats
import json

from nova import context

from nova.objects import register_all
import nova.objects from oslo_config
import cfg from nova
import config from nova.compute.api
import API
import sys
from oslo_log import log as logging
from nova.db import api as db
from nova.db.sqlalchemy import api as sqlapi
from nova.db.sqlalchemy import models
from sqlalchemy.orm import undefer
from sqlalchemy.orm import joinedload

def register_opts(conf):     conf.register_cli_opt(
        cfg.StrOpt(
            'my_host'
        )
    )
    conf.register_cli_opt(
        cfg.IntOpt(
            "times",
            default=1
        )
    )
    conf.register_cli_opt(
        cfg.IntOpt(
            "limit",
            default=10
        )
    )
    conf.register_cli_opt(
        cfg.IntOpt(
            "step-size",
            default=10
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            "output",
            default="/tmp/results"
        )     )
def init():
    # register objects
    register_all()
    register_opts(cfg.CONF)
    config.parse_args(sys.argv)
    logging.setup(cfg.CONF, "dev-demo")
def warm_up():
    inst_list = db.instance_get_all_by_filters_sort(
        context.get_admin_context(),

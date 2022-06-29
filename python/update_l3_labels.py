#!/usr/bin/env python

"""
This example demonstrates the following:
    - Restart pods directly and wait
    - Restart pods by patching node-label and wait pod stats
"""

import logging
from kubernetes import client, config, watch
from concurrent.futures import FIRST_COMPLETED
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
import json
import base64
from oslo_config import cfg
import socket
import sys
import time


# global configuration
POOL_SIZE = 10
POD_START_TIMEOUT = 240
LOG_SYMBOL = "neutron_inspur.agents.acl.l3.acl_l3_agent [-] Process router add, router_id"


logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


def init():
    register_opts(cfg.CONF)


def register_opts(conf):
    conf.register_cli_opt(
        cfg.StrOpt(
            'oldSelector',
            required=True,
            help='old node selector labels'
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'newSelector',
            required=True,
            help='new node selector labels'
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'namespace',
            required=True,
            default='openstack',
            help='namespace of resource'
        )
    )
    conf.register_cli_opt(
        cfg.IntOpt(
            'maxWorkers',
            default=1,
            help='step size of pod restarting'
        )
    )
    conf.register_cli_opt(
        cfg.BoolOpt(
            'onlyRestartPod',
            default=False,
            help='step size of pod restarting'
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'rsType',
            default="daemonset",
            help='step size of pod restarting'
        )
    )
    # init
    conf(
        project='update-l3-labels'
    )


class PodHandler(object):
    def __init__(self, hostname, oldlabel=None, newlabel=None):
        config.load_kube_config()
        self.api_instance = client.CoreV1Api()
        self.hostname = hostname
        if oldlabel is not None:
            self.oldlabel = oldlabel
        if newlabel is not None:
            self.newlabel = newlabel
        self.pods = []
        self.launcher_pod = []

    def list_pods(self):
        pod_list = self.api_instance.\
            list_namespaced_pod(namespace=cfg.CONF.namespace,
                                field_selector="spec.nodeName" + "=" + self.hostname,
                                label_selector=cfg.CONF.oldSelector)
        return pod_list.items

    def _patch_node_label_and_wait(self, key, value, status):
        body = {
            "metadata": {
                "labels": {
                    key: value}
            }
        }
        self.api_instance.patch_node(self.hostname, body)
        for pod in self.pods:
            self._wait_pod_state(pod.metadata.name, status)

    def _terminate_pods(self):
        old_pods = self.list_pods()
        for pod in old_pods:
            self.api_instance.delete_namespaced_pod(pod.metadata.name,
                                                    cfg.CONF.namespace)
            self._wait_pod_state(pod.metadata.name)

    def _wait_pod_state(self, pod_id, tgt_state):
        start_time = time.time()
        if tgt_state == 'deleted':
            while time.time() - start_time < POD_START_TIMEOUT:
                pass
        if tgt_state == 'running':
            return pod_id
            pass

    def manage_pod(self):
        if cfg.CONF.onlyRestartPod:
            self._terminate_pods()
            return
        # terminate pod by removing old label
        key, value = self.oldlabel.split('=')
        self._patch_node_label_and_wait(key, None, 'deleted')
        # start pod by patching new label
        key, value = self.newlabel.split('=')
        self._patch_node_label_and_wait(key, value, 'running')

    def get_logs(self):
        w = watch.Watch()

        for line in w.stream(self.api_instance.read_namespaced_pod_log,
                             name=self.launcher_pod,
                             namespace=cfg.CONF.namespace,
                             timestamps=True):
            if LOG_SYMBOL in line:
                # Once we get the symbol log, return true.
                print(line, end="\n")
                return True
            # print(line, end="\n")
            # if "INFO:: Training completed." in line:


class ThreadPoolExecutorWithLimit(ThreadPoolExecutor):
    def __init__(self, max_workers):
        self._task_futures = set()
        self._limit = max_workers
        LOG.debug("max_workers: %s", max_workers)
        super(ThreadPoolExecutorWithLimit, self).__init__(max_workers)

    def submit(self, fn, *args, **kwargs):
        if len(self._task_futures) >= self._limit:
            done, self._task_futures = wait(self._task_futures,
                                            return_when=FIRST_COMPLETED)
        future = super(ThreadPoolExecutorWithLimit, self).submit(fn, *args,
                                                                 **kwargs)
        self._task_futures.add(future)
        return future


def main():
    init()

    config.load_kube_config()

    api_instance = client.CoreV1Api()

    # Listing the nodes that matching label selector
    node_list = api_instance.list_node(label_selector=cfg.CONF.oldSelector)

    # print("%s\t\t%s" % ("NAME", "LABELS"))

    executor = ThreadPoolExecutorWithLimit(max_workers=cfg.CONF.maxWorkers)

    for node in node_list.items():
        ph = PodHandler(node.metadata.name, cfg.CONF.oldSelector, cfg.CONF.newSelector)
        executor.submit(ph.manage_pod)


if __name__ == '__main__':
    main()


# kubectl get pods -n openstack --field-selector spec.nodeName=compute-001 -l application=neutron,component=l3-agent


# Usage:
#
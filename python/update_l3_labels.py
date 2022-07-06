#!/usr/bin/env python

"""
This example demonstrates the following:
    - Restart pods directly and wait
    - Restart pods by patching node-label and wait pod stats
"""

import logging
from kubernetes import client, config, watch
from concurrent.futures import FIRST_COMPLETED, ALL_COMPLETED, FIRST_EXCEPTION
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
import json
import base64
from oslo_config import cfg
import socket
import sys
import time
import paramiko


# global configuration
POOL_SIZE = 10
POD_START_TIMEOUT = 240
SSH_PORT = 6233
SSH_USER = "root"
SSH_PKEY = "/etc/kubernetes/common/private_key"
SSH_PASSWD = None

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
            help='resource controller type'
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'metadataLabel',
            required=True,
            default="",
            help='metadata label of pod'
        )
    )
    # init
    conf(
        project='update-l3-labels'
    )


def ssh_connect(hostname):
    ssh = paramiko.SSHClient()
    cmd = "ip netns |grep qrouter-"
    private_key = paramiko.RSAKey.from_private_key_file(SSH_PKEY)
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=hostname, port=SSH_PORT, username=SSH_USER, password=SSH_PASSWD, pkey=private_key)
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.readlines()
    err = stderr.readlines()
    ssh.close()
    return out, err


class PodHandler(object):
    def __init__(self, hostname, oldlabel=None, newlabel=None):
        config.load_kube_config()
        self.api_instance = client.CoreV1Api()
        self.watch = watch.Watch
        self.hostname = hostname
        if oldlabel is not None:
            self.oldlabel = oldlabel
        if newlabel is not None:
            self.newlabel = newlabel
        self.pods = []
        self.launcher_pod = []

    def list_pods(self):
        # list namespaced pods
        pod_list = self.api_instance.\
            list_namespaced_pod(namespace=cfg.CONF.namespace,
                                field_selector="spec.nodeName" + "=" + self.hostname,
                                label_selector=cfg.CONF.metadataLabel)
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
            self._wait_pod_state(pod.metadata.name, "running")

    def _wait_pod_state(self, pod_id, tgt_state):
        start_time = time.time()
        if tgt_state == 'deleted':
            while time.time() - start_time < POD_START_TIMEOUT:
                try:
                    self.api_instance.read_namespaced_pod(pod_id, cfg.CONF.namespace)
                except client.exceptions.ApiException as e:
                    if e.reason == "Not Found":
                        LOG.info("pod %s deleted successfully")
                        break
            else:
                LOG.error("pod %s did not successfully remove after %d seconds.", pod_id, POD_START_TIMEOUT)
                raise Exception

        if tgt_state == 'running':
            while time.time() - start_time < POD_START_TIMEOUT:
                pod_ready = self._watch_pod_state(pod_id)
                if pod_ready:
                    break
            else:
                LOG.error("pod %s did not reach state running start after %d seconds.", POD_START_TIMEOUT)
                raise Exception

    def _watch_pod_state(self, pod):
        for event in self.watch.stream(self.list_pods()):
            event_type = event['type'].upper()
            pod_name = event['object'].metadata.name
            if event_type in {'ADDED', 'MODIFIED'}:
                status = event['object'].status
                if pod_name != pod:
                    pod_ready = True
                    if LOG_SYMBOL:
                        pod_ready = self.get_logs(pod_name)
                    else:
                        pod_phase = status.phase
                        if (pod_phase == 'Succeeded' or
                                (pod_phase == 'Running' and
                                 self._get_pod_condition(
                                     status.conditions, 'Ready') == 'True')):
                            LOG.info('Pod %s is ready!', pod_name)
                        else:
                            pod_ready = False
                    return pod_ready
            elif event_type == 'ERROR':
                LOG.error('Pod %s: Got error event %s', pod_name, event['object'].to_dict())
                raise Exception('Got error event for pod: %s' % event['object'])
            else:
                LOG.error('Unrecognized event type (%s) for pod: %s',
                          event_type, event['object'])
                raise Exception(
                    'Got unknown event type (%s) for pod: %s'
                    % (event_type, event['object']))

    def _get_pod_condition(self, pod_conditions, condition_type):
        for pc in pod_conditions:
            if pc.type == condition_type:
                return pc.status

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

    def get_logs(self, pod_name):

        for line in self.watch.stream(self.api_instance.read_namespaced_pod_log,
                                      name=pod_name,
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
                                            return_when=ALL_COMPLETED)
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
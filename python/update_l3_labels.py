#!/usr/bin/env python

"""
This example demonstrates the following:
    - Restart pods directly and wait
    - Restart pods by patching node-label and wait pod stats
"""


import fcntl
import logging
from kubernetes import client, config, watch
from concurrent.futures import FIRST_COMPLETED, ALL_COMPLETED, FIRST_EXCEPTION
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
from multiprocessing import Pool
import json
import base64
from oslo_config import cfg
import socket
import sys
import time
import paramiko
import os


WORKSPACE = '/opt/restart_pods'
if not os.path.exists(WORKSPACE):
    os.makedirs(WORKSPACE)
FILE_SUCCESS = os.path.join(WORKSPACE, 'node_success')
FILE_FAILED = os.path.join(WORKSPACE, 'node_failed')


# global configuration
POOL_SIZE = 10
POD_START_TIMEOUT = 240
SSH_PORT = 6233
SSH_USER = "root"
SSH_PKEY = "/etc/kubernetes/common/private_key"
SSH_PASSWD = None

# LOG_SYMBOL = "neutron_inspur.agents.acl.l3.acl_l3_agent [-] Process router add, router_id"
LOG_SYMBOL = ""

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


def init():
    register_opts(cfg.CONF)
    if not cfg.CONF.onlyRestartPod and not cfg.CONF.newSelector:
        LOG.error("newSelector need be given when NOT onlyRestartPod")
        raise Exception


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
            default="",
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


def ssh_get_qrouter(hostname):
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
        self.hostname = hostname
        if oldlabel is not None:
            self.oldlabel = oldlabel
        if newlabel is not None:
            self.newlabel = newlabel
        # get old pods
        self.pods = self.list_pods()
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
        for pod in self.pods:
            LOG.info("delete pod %s", pod.metadata.name)
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
                        LOG.info("pod %s deleted successfully", pod_id)
                        break
                    else:
                        raise
            else:
                LOG.error("pod %s did not successfully remove after %d seconds.", pod_id, POD_START_TIMEOUT)
                raise Exception

        if tgt_state == 'running':
            pod_ready = self._watch_pod_state(pod_id)
            if pod_ready:
                pass
            else:
                # LOG.error("pod %s did not reach state running start after %d seconds.", POD_START_TIMEOUT)
                raise Exception

    def _watch_pod_state(self, pod):
        w = watch.Watch()
        pod_ready = False
        for event in w.stream(self.api_instance.list_namespaced_pod,
                              namespace=cfg.CONF.namespace,
                              field_selector="spec.nodeName" + "=" + self.hostname,
                              label_selector=cfg.CONF.metadataLabel,
                              timeout_seconds=POD_START_TIMEOUT):
            event_type = event['type'].upper()
            pod_name = event['object'].metadata.name
            if event_type in {'ADDED', 'MODIFIED'}:
                status = event['object'].status
                if pod_name != pod:
                    pod_phase = status.phase
                    if (pod_phase == 'Succeeded' or
                            (pod_phase == 'Running' and
                             self._get_pod_condition(
                                 status.conditions, 'Ready') == 'True')):
                        if LOG_SYMBOL and ssh_get_qrouter(self.hostname):
                            return self.get_logs(pod_name)
                        else:
                            LOG.info('Pod %s is ready!', pod_name)
                            return True
                    else:
                        continue
            elif event_type == 'ERROR':
                LOG.error('Pod %s: Got error event %s', pod_name, event['object'].to_dict())
                raise Exception('Got error event for pod: %s' % event['object'])
        else:
            return pod_ready
            # else:
                # LOG.error('Unrecognized event type (%s) for pod: %s',
                #           event_type, event['object'])
                # raise Exception(
                #     'Got unknown event type (%s) for pod: %s'
                #     % (event_type, event['object']))

    def _get_pod_condition(self, pod_conditions, condition_type):
        for pc in pod_conditions:
            if pc.type == condition_type:
                return pc.status

    def manage_pod(self):
        if cfg.CONF.onlyRestartPod:
            try:
                self._terminate_pods()
                write_result_to_file(self.hostname, FILE_SUCCESS)
            except Exception as e:
                LOG.error('terminating pods meets error: %s', e)
                logging.exception(e)
                write_result_to_file(self.hostname, FILE_FAILED)
                raise

        else:
            try:
                # terminate pod by removing old label
                key, value = self.oldlabel.split('=')
                self._patch_node_label_and_wait(key, None, 'deleted')
                # start pod by patching new label
                key, value = self.newlabel.split('=')
                self._patch_node_label_and_wait(key, value, 'running')
                write_result_to_file(self.hostname, FILE_SUCCESS)
            except Exception as e:
                LOG.error('patch node to restart pods meets error: %s', e)
                logging.exception(e)
                write_result_to_file(self.hostname, FILE_FAILED)
                raise

    def get_logs(self, pod_name):
        start_time = time.time()
        w = watch.Watch()
        for line in w.stream(self.api_instance.read_namespaced_pod_log,
                             name=pod_name,
                             namespace=cfg.CONF.namespace,
                             timestamps=True):
            if LOG_SYMBOL in line:
                # Once we get the symbol log, return true.
                print(line, end="\n")
                LOG.info('Pod %s is ready!', pod_name)
                return True
            if time.time() - start_time > POD_START_TIMEOUT - 5:
                LOG.error('Pod %s never get expected log after %d seconds!', pod_name, POD_START_TIMEOUT - 5)
                w.stop()
                return False
        # else:
        #     return False
        #     # print(line, end="\n")
        #     # if "INFO:: Training completed." in line:


def write_result_to_file(node, file):
    with open(file, encoding='utf-8', mode='a') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(node + '\n')


def read_file(path):
    with open(path, 'r') as f:
        lines = f.readlines()
        dict_tag_list = []
        for line in lines:
            line = line.strip('\n')
            dict_tag_list.append(line)
    return dict_tag_list


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

    for node in node_list.items:
        done_nodes = read_file(FILE_SUCCESS)
        if node.metadata.name not in done_nodes:
            ph = PodHandler(node.metadata.name, cfg.CONF.oldSelector, cfg.CONF.newSelector)
            executor.submit(ph.manage_pod)


if __name__ == '__main__':
    main()


# kubectl get pods -n openstack --field-selector spec.nodeName=compute-001 -l application=neutron,component=l3-agent


# Usage:

# restart pods by update labels:
# python3 update_l3_labels.py --metadataLabel "application=neutron,component=l3-agent" --oldSelector "node-role.kubernetes.io/l3-node=enabled" --newSelector "node-role.kubernetes.io/l3-node=for-upgrade" --maxWorkers 3

# just restart pods:
# python3 update_l3_labels.py --metadataLabel "application=neutron,component=l3-agent"
# --oldSelector "node-role.kubernetes.io/l3-node=enabled"
# --onlyRestartPod

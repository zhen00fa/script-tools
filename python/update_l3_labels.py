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


WORKSPACE = '/opt/restart_pods/'
if not os.path.exists(WORKSPACE):
    os.makedirs(WORKSPACE)
FILE_SUCCESS = os.path.join(WORKSPACE, 'node_success')
FILE_FAILED = os.path.join(WORKSPACE, 'node_failed')
if not os.path.exists(FILE_SUCCESS):
    file = open(FILE_SUCCESS, 'w')
    file.close()
if not os.path.exists(FILE_FAILED):
    file = open(FILE_FAILED, 'w')
    file.close()


# global configuration
POOL_SIZE = 10
POD_START_TIMEOUT = 600
SSH_PORT = 6233
SSH_USER = "root"
SSH_PKEY = "/etc/kubernetes/common/private_key"
SSH_PASSWD = None

LOG_SYMBOL = ""
# 3.1.x
# LOG_SYMBOL = "neutron_inspur.agents.acl.l3.acl_l3_agent [-] Process router add, router_id"
# After 3.5
# LOG_SYMBOL = "Finished a router update for"

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)
fh = logging.FileHandler(WORKSPACE + 'update_l3_labels.log')
fh.setLevel(logging.INFO)
LOG.addHandler(fh)

# load k8s config
KUBE_CONFIG_FILE = None


def init():
    register_opts(cfg.CONF)
    if not cfg.CONF.onlyRestartPod and not cfg.CONF.newSelector:
        LOG.error("newSelector need be given when NOT onlyRestartPod")
        raise Exception
    if cfg.CONF.matchLog and not LOG_SYMBOL:
        LOG.error("Restarting pod need match log, but no symbol log provided")
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
            help=''
        )
    )
    conf.register_cli_opt(
        cfg.BoolOpt(
            'matchLog',
            default=False,
            help=''
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
    conf.register_cli_opt(
        cfg.FloatOpt(
            'icpVersion',
            required=True,
            # default=3.1,
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
    if out:
        return True
    else:
        return False


class PodHandler(object):
    def __init__(self, hostname, oldlabel=None, newlabel=None):
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
        config.load_kube_config(config_file=KUBE_CONFIG_FILE)
        api_instance = client.CoreV1Api()
        pod_list = api_instance.\
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
        if cfg.CONF.icpVersion >= 3.5:
            edit_cke_node(self.hostname, key, value)
        else:
            config.load_kube_config(config_file=KUBE_CONFIG_FILE)
            api_instance = client.CoreV1Api()
            api_instance.patch_node(self.hostname, body)
        for pod in self.pods:
            self._wait_pod_state(pod.metadata.name, status)

    def _terminate_pods(self):
        config.load_kube_config(config_file=KUBE_CONFIG_FILE)
        api_instance = client.CoreV1Api()
        for pod in self.pods:
            LOG.info("delete pod %s", pod.metadata.name)
            api_instance.delete_namespaced_pod(pod.metadata.name,
                                               cfg.CONF.namespace)
            self._wait_pod_state(pod.metadata.name, "running")

    def _wait_pod_state(self, pod_id, tgt_state):
        config.load_kube_config(config_file=KUBE_CONFIG_FILE)
        api_instance = client.CoreV1Api()
        start_time = time.time()
        if tgt_state == 'deleted':
            while time.time() - start_time < POD_START_TIMEOUT:
                try:
                    api_instance.read_namespaced_pod(pod_id, cfg.CONF.namespace)
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
        config.load_kube_config(config_file=KUBE_CONFIG_FILE)
        api_instance = client.CoreV1Api()
        pod_ready = False
        new_pod_name = ""
        need_get_log = False
        for event in w.stream(api_instance.list_namespaced_pod,
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
                        need_get_log = cfg.CONF.matchLog and ssh_get_qrouter(self.hostname)
                        if need_get_log:
                            new_pod_name = pod_name
                            w.stop()
                            break
                        else:
                            LOG.info('Pod %s is ready!', pod_name)
                            w.stop()
                            return True
                    else:
                        continue
            elif event_type == 'ERROR':
                w.stop()
                LOG.error('Pod %s: Got error event %s', pod_name, event['object'].to_dict())
                raise Exception('Got error event for pod: %s' % event['object'])
        if need_get_log:
            pod_ready = get_logs(new_pod_name)
        return pod_ready

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
                LOG.info("remove label %s on node %s", self.oldlabel, self.hostname)
                self._patch_node_label_and_wait(key, None, 'deleted')
                # start pod by patching new label
                key, value = self.newlabel.split('=')
                LOG.info("add label %s on node %s", self.newlabel, self.hostname)
                self._patch_node_label_and_wait(key, value, 'running')
                write_result_to_file(self.hostname, FILE_SUCCESS)
            except Exception as e:
                LOG.error('patch node to restart pods meets error: %s', e)
                logging.exception(e)
                write_result_to_file(self.hostname, FILE_FAILED)
                raise


def edit_cke_node(node_name, label, val):
    config.load_kube_config(config_file=KUBE_CONFIG_FILE)
    api_exten = client.CustomObjectsApi()
    try:
        body = {
            "metadata": {
                "labels": {
                    label: val
                }
            }
        }
        api_exten.patch_namespaced_custom_object(group="cke.inspur.com", version="v1alpha1",
                                                 namespace="kube-system",
                                                 plural="ckenodes", name=node_name,
                                                 body=body)
    except client.exceptions.ApiException as e:
        if e.reason == "Not Found":
            LOG.info("Cke node $s not defined", node_name)


def get_logs(pod_name):
    config.load_kube_config(config_file=KUBE_CONFIG_FILE)
    api_instance = client.CoreV1Api()
    start_time = time.time()
    w = watch.Watch()
    for line in w.stream(api_instance.read_namespaced_pod_log,
                         name=pod_name,
                         namespace=cfg.CONF.namespace,
                         timestamps=True):
        if LOG_SYMBOL in line:
            # Once we get the symbol log, return true.
            print(line, end="\n")
            w.stop()
            LOG.info('Get symbol log! Pod %s is ready!', pod_name)
            return True
        if time.time() - start_time > POD_START_TIMEOUT - 5:
            LOG.error('Pod %s never get expected log after %d seconds!', pod_name, POD_START_TIMEOUT - 5)
            w.stop()
            return False


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
        self._fail_futures = set()
        LOG.debug("max_workers: %s", max_workers)
        super(ThreadPoolExecutorWithLimit, self).__init__(max_workers)

    def submit(self, fn, *args, **kwargs):
        if len(self._task_futures) >= self._limit:
            done, self._task_futures = wait(self._task_futures,
                                            return_when=FIRST_COMPLETED)
            for future in done:
                worker_exception = future.exception()
                if worker_exception:
                    logging.exception("Worker return exception: {}".format(worker_exception))
                    self._fail_futures.add(future)
            if self._fail_futures:
                self.shutdown()

        future = super(ThreadPoolExecutorWithLimit, self).submit(fn, *args,
                                                                 **kwargs)
        self._task_futures.add(future)
        return future


def main():
    init()
    config.load_kube_config(config_file=KUBE_CONFIG_FILE)
    api_instance = client.CoreV1Api()
    # Listing the nodes that match label selector
    node_list = api_instance.list_node(label_selector=cfg.CONF.oldSelector)

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

# restart pods by updating labels:
# python3 update_l3_labels.py --metadataLabel "application=neutron,component=l3-agent"
# --oldSelector "node-role.kubernetes.io/l3-node=enabled"
# --newSelector "node-role.kubernetes.io/l3-node=for-upgrade"
# --maxWorkers 3

# just restart pods:
# python3 update_l3_labels.py --metadataLabel "application=neutron,component=l3-agent"
# --oldSelector "node-role.kubernetes.io/l3-node=enabled"
# --onlyRestartPod

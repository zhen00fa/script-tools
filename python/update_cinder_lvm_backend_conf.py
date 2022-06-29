#!/usr/bin/env python

"""
This example demonstrates the following:
    - Update secret by patch method.
"""

import logging
from kubernetes import client, config
import base64


logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__file__)


lvm_nodes = ['compute367', 'compute360', 'compute357', 'compute358', 'compute361', 'compute356', 'compute350',
             'compute351', 'compute352', 'compute362', 'compute353', 'compute354', 'compute355', 'compute365',
             'compute366', 'compute359', 'compute363', 'compute368', 'compute369', 'compute370', 'compute371',
             'compute372', 'compute373', 'compute374', 'compute375', 'compute376', 'compute377', 'compute414',
             'compute417', 'compute415', 'compute416', 'compute407', 'compute410', 'compute409', 'compute403',
             'compute412', 'compute405', 'compute404', 'compute411', 'compute406', 'compute408', 'compute413',
             'compute701', 'compute702', 'compute703', 'compute704']


legal_ds = """
cinder-volume-07e1aqeewf
cinder-volume-0f6yetptc4
cinder-volume-0jrlc8bzh3
cinder-volume-1bqz1tsyvk
cinder-volume-1u1upiquuy
cinder-volume-4h5pdz0mns
cinder-volume-6ig1hfakis
cinder-volume-6vb3yfl4zj
cinder-volume-8sof3ohby5
cinder-volume-9fgu9hchvn
cinder-volume-9ldqdaq5et
cinder-volume-9m4hwhnszl
cinder-volume-9ptsullx44
cinder-volume-a6p5onwhho
cinder-volume-ack9yg3cfm
cinder-volume-al9njjzpbc
cinder-volume-bk6iwwekkl
cinder-volume-ckre1bivlp
cinder-volume-dvs7o6omcy
cinder-volume-e05ankcnxs
cinder-volume-ei1ooh7zls
cinder-volume-fj7qdswggk
cinder-volume-fz1ajf2cnf
cinder-volume-h5mvanhtkf
cinder-volume-hjrcwitu6v
cinder-volume-ijvcm6qjbp
cinder-volume-jqmmdlq6a9
cinder-volume-kfslzneh09
cinder-volume-khpjyw9zhw
cinder-volume-ki4x99hh4x
cinder-volume-ks9nnueyia
cinder-volume-lhci8o9g1v
cinder-volume-ln2gvxfcb4
cinder-volume-ngb2sluxgv
cinder-volume-nz0uu9mue8
cinder-volume-ohtt7ws4fa
cinder-volume-peffprig4j
cinder-volume-pmfkz5suxt
cinder-volume-qgqngk0vlo
cinder-volume-sfpfnvd7df
cinder-volume-v0cztc69bd
cinder-volume-v9qfbnkvrx
cinder-volume-vhwg1qygpe
cinder-volume-y8pvzasylc
cinder-volume-yfla01o79q
cinder-volume-zj6o8nbbvk
"""

legal_ds = [line for line in legal_ds.strip().split('\n')]

data_tmpl = {'data': {'backends.conf': '%s'}}

# global vars
additional_parameter = 'volume_clear_size = 1'
PURGE_OLD_DS = False  # 如果要同时删除旧的ds，请设置为true


# def compare_secret(old, new):
#     if old and new:
#         data_old = str(base64.b64decode(old), "utf-8")
#         data_new = str(base64.b64decode(new), "utf-8")
#         set_old = set([line for line in data_old.strip().split('\n')])
#         set_new = set([line for line in data_new.strip().split('\n')])
#         if len(set_old - set_new) == 2:
#             str1 = str(set_old - set_new)
#             if additional_parameter[0] in str1:
#                 if additional_parameter[1] in str1:
#                     return True
#         else:
#             LOG.error("Compare secrets %s %s failed, please check", data_old, data_new)
#     return False


# def patch_secret(v1, legal_secret_name, illegal_secret_name):
#     illegal_secret = v1.read_namespaced_secret(illegal_secret_name, "openstack")
#     if not illegal_secret:
#         raise Exception("Secret %s does not exist", illegal_secret_name)
#     legal_secret = v1.read_namespaced_secret(legal_secret_name, "openstack")
#     if not legal_secret:
#         raise Exception("Secret %s does not exist", legal_secret_name)
#     data1 = illegal_secret.data.get('backends.conf')
#     data2 = legal_secret.data.get('backends.conf')
#     if data1 and data2:
#         if compare_secret(data1, data2):
#             body = json.dump(data_tmpl) % data1
#             v1.patch_namespaced_secret(legal_secret_name, "openstack", body)
#         else:
#             raise Exception
#     else:
#         raise Exception("Secret do not have sub-secret backends.conf")

def handle_secret(new):
    data_1 = str(base64.b64decode(new), "utf-8")
    new_List = [line for line in data_1.strip().split('\n')]
    index = new_List.index('volume_driver = cinder.volume.drivers.lvm.LVMVolumeDriver')
    new_List.insert(index, additional_parameter)
    data2 = ""
    for i in new_List:
        data2 = data2 + i + '\n'
    print(data2)
    return base64.b64encode(data2.encode("utf-8")).decode("utf-8")


def compare_secret(new):
    if new:
        data_new = str(base64.b64decode(new), "utf-8")
        set_new = set([line for line in data_new.strip().split('\n')])
        if additional_parameter not in set_new:
            return True
        else:
            LOG.warning("%s already exist", additional_parameter)
    return False


def patch_secret(v1, legal_secret_name):
    # illegal_secret = v1.read_namespaced_secret(illegal_secret_name, "openstack")
    # if not illegal_secret:
    #     raise Exception("Secret %s does not exist", illegal_secret_name)
    LOG.info("Patching secret %s", legal_secret_name)
    legal_secret = v1.read_namespaced_secret(legal_secret_name, "openstack")
    if not legal_secret:
        raise Exception("Secret %s does not exist", legal_secret_name)
    # data1 = illegal_secret.data.get('backends.conf')
    data2 = legal_secret.data.get('backends.conf')
    if data2:
        if compare_secret(data2):
            newsecret = handle_secret(data2)
            data_tmpl["data"]["backends.conf"] = newsecret
            v1.patch_namespaced_secret(legal_secret_name, "openstack", body=data_tmpl)
        else:
            raise Exception
    else:
        raise Exception("Secret do not have sub-secret backends.conf")


def main():
    config.load_kube_config()
    v1 = client.CoreV1Api()
    app1 = client.AppsV1Api()

    for node in lvm_nodes:
        pod_list = v1.list_namespaced_pod(namespace="openstack",
                                          field_selector="spec.nodeName" + "=" + node,
                                          label_selector="application=cinder,component=volume")
        if pod_list:
            tmp_podname_list = [pod.metadata.name for pod in pod_list.items]
            if len(pod_list.items) == 1:
                continue
            if len(pod_list.items) >= 2:
                raise Exception("Pod num not right on node %s, skip.", node)

            tmp_secrets = [podname.rsplit("-", 1)[0] for podname in tmp_podname_list]
            if tmp_secrets[0] in legal_ds:
                legal_secret = tmp_secrets[0]
                if tmp_secrets[1] in legal_ds:
                    LOG.error("Both pods on node %s are new", node)
                    continue
                else:
                    illegal_secret = tmp_secrets[1]
            else:
                illegal_secret = tmp_secrets[0]
                if tmp_secrets[1] in legal_ds:
                    legal_secret = tmp_secrets[1]
                else:
                    LOG.error("Both pods on node %s are not new", node)
                    continue
            try:
                LOG.info("Start handling resource on node %s", node)
                patch_secret(v1, legal_secret)
                legal_pod = next((i for i in tmp_podname_list if i.startswith(legal_secret)), None)
                LOG.info("Restarting pod for daemonset %s", legal_secret)
                v1.delete_namespaced_pod(legal_pod, "openstack")
                if PURGE_OLD_DS:
                    LOG.info("Deleting secret %s", illegal_secret)
                    v1.delete_namespaced_secret(illegal_secret, "openstack")
                    LOG.info("Deleting daemonset %s", illegal_secret)
                    app1.delete_namespaced_daemon_set(illegal_secret, "openstack")
            except Exception as e:
                print(e)
                LOG.warning("Skip on node %s", node)
                continue


if __name__ == '__main__':
    main()

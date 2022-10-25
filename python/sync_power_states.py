import base64
import binascii
import contextlib
import copy
import functools
import inspect
import sys
import time
import traceback
import typing as ty

from cinderclient import exceptions as cinder_exception
from cursive import exception as cursive_exception
import eventlet.event
from eventlet import greenthread
import eventlet.semaphore
import eventlet.timeout
import futurist
from keystoneauth1 import exceptions as keystone_exception
import os_traits
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_serialization import jsonutils
from oslo_service import loopingcall
from oslo_service import periodic_task
from oslo_utils import excutils
from oslo_utils import strutils
from oslo_utils import timeutils
from oslo_utils import units
import six
from six.moves import range

from nova.accelerator import cyborg
from nova import block_device
from nova.compute import api as compute
from nova.compute import build_results
from nova.compute import claims
from nova.compute import power_state
from nova.compute import resource_tracker
from nova.compute import rpcapi as compute_rpcapi
from nova.compute import task_states
from nova.compute import utils as compute_utils
from nova.compute.utils import wrap_instance_event
from nova.compute import vm_states
from nova import conductor
import nova.conf
import nova.context
from nova import exception
from nova import exception_wrapper
from nova.i18n import _
from nova.image import glance
from nova import manager
from nova.network import model as network_model
from nova.network import neutron
from nova import objects
from nova.objects import base as obj_base
from nova.objects import external_event as external_event_obj
from nova.objects import fields
from nova.objects import instance as obj_instance
from nova.objects import migrate_data as migrate_data_obj
from nova.pci import request as pci_req_module
from nova.pci import whitelist
from nova import rpc
from nova import safe_utils
from nova.scheduler.client import query
from nova.scheduler.client import report
from nova.scheduler import utils as scheduler_utils
from nova import utils
from nova.virt import block_device as driver_block_device
from nova.virt import configdrive
from nova.virt import driver
from nova.virt import event as virtevent
from nova.virt import hardware
from nova.virt import storage_users
from nova.virt import virtapi
from nova.volume import cinder

LOG = logging.getLogger(__name__)

ctx = context.get_admin_context()

@periodic_task.periodic_task(spacing=600, run_immediately=True)
def _sync_power_states(self, context=ctx):
    """Align power states between the database and the hypervisor.
    To sync power state data we make a DB call to get the number of
    virtual machines known by the hypervisor and if the number matches the
    number of virtual machines known by the database, we proceed in a lazy
    loop, one database record at a time, checking if the hypervisor has the
    same power state as is in the database.
    """
    db_instances = objects.InstanceList.get_by_host(context, self.host,
                                                    expected_attrs=[],
                                                    use_slave=True)
    try:
        num_vm_instances = self.driver.get_num_instances()
    except exception.VirtDriverNotReady as e:
        # If the virt driver is not ready, like ironic-api not being up
        # yet in the case of ironic, just log it and exit.
        LOG.info('Skipping _sync_power_states periodic task due to: %s', e)
        return
    num_db_instances = len(db_instances)
    if num_vm_instances != num_db_instances:
        LOG.warning("While synchronizing instance power states, found "
                    "%(num_db_instances)s instances in the database "
                    "and %(num_vm_instances)s instances on the "
                    "hypervisor.",
                    {'num_db_instances': num_db_instances,
                     'num_vm_instances': num_vm_instances})
    def _sync(db_instance):
        # NOTE(melwitt): This must be synchronized as we query state from
        #                two separate sources, the driver and the database.
        #                They are set (in stop_instance) and read, in sync.
        @utils.synchronized(db_instance.uuid)
        def query_driver_power_state_and_sync():
            self._query_driver_power_state_and_sync(context, db_instance)
        try:
            query_driver_power_state_and_sync()
        except Exception:
            LOG.exception("Periodic sync_power_state task had an "
                          "error while processing an instance.",
                          instance=db_instance)
        self._syncs_in_progress.pop(db_instance.uuid)
    for db_instance in db_instances:
        # process syncs asynchronously - don't want instance locking to
        # block entire periodic task thread
        uuid = db_instance.uuid
        if uuid in self._syncs_in_progress:
            LOG.debug('Sync already in progress for %s', uuid)
        else:
            LOG.debug('Triggering sync for uuid %s', uuid)
            self._syncs_in_progress[uuid] = True
            self._sync_power_pool.spawn_n(_sync, db_instance)
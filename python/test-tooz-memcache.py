from tooz import coordination
from tooz.drivers import memcached as mem1
from oslo_utils import timeutils
import uuid
import tooz
import tenacity
from tenacity import *
import logging
import threading
import functools
import pdb


LOG = logging.getLogger(__name__)


_default_retry = (
    tenacity.retry_if_exception_type(
        coordination.ToozConnectionError) |
    tenacity.retry_if_exception_type(
        tooz.ToozError))

_default_wait = wait.wait_exponential(max=1)


LOCK_TIMEOUT = 30
# url = "memcached://memcached.openstack.svc.region-stackdev.myinspurcloud.com:11211"
url = "memcached://10.110.29.1:11212"
member_id = ("cinder-" + str(uuid.uuid4())).encode('ascii')
coordinator = coordination.get_coordinator(
    url, member_id, lock_timeout=LOCK_TIMEOUT
)
coordinator.start(start_heart=True)

lock_name = "uuid-delete_snasphot".encode("ascii")

# to produce a lock
lock = coordinator.get_lock(lock_name)


def test_retry(stop_max_delay=None, **kwargs):
    k = {"wait": _default_wait, "retry": lambda x: False}
    if kwargs:
        for key in kwargs:
            k[key] = kwargs[key]
    if stop_max_delay not in (True, False, None):
        k['stop'] = stop.stop_after_delay(stop_max_delay)
    return tenacity.retry(**k)


# @_retry.retry(stop_max_delay=True)
# @retry(wait=wait.wait_exponential(max=1), retry=lambda x: False)
# @retry(wait=wait.wait_exponential(max=1),
#        # retry=retry_if_exception_type(coordination.ToozConnectionError),
#        retry=_default_retry,
#        stop=stop_after_attempt(5), reraise=True)
@test_retry(stop_max_delay=True, retry=_default_retry, reraise=True)
@mem1._translate_failures
def _acquire():
    print("trying add lock %s", lock.name)
    if lock.coord.client.add(
            lock.name,
            lock.coord._member_id,
            expire=LOCK_TIMEOUT,
            noreply=False):
        lock.coord._acquired_locks.append(lock)
        print("add lock success")
        return True
    raise TryAgain


@test_retry(stop_max_delay=True, retry=_default_retry, reraise=True)
@mem1._translate_failures
def _release():
    print("trying release lock %s", lock.name)
    if not lock.acquired:
        return False
    if lock not in lock.coord._acquired_locks:
        return False

    value = lock.coord.client.get(lock.name)
    if value != lock.coord._member_id:
        lock.coord._acquired_locks.remove(lock)
        return False
    else:
        # NOTE(zhen): Whether 'was_deleted' is 'TRUE' or not,
        # eventually we have to remove self from '_acquired_locks'.
        was_deleted = lock.coord.client.delete(lock.name,
                                               noreply=False)
        lock.coord._acquired_locks.remove(lock)
        return was_deleted


@mem1._translate_failures
def _release_1():
    print("trying release lock %s", lock.name)
    if not lock.acquired:
        return False
    if lock not in lock.coord._acquired_locks:
        return False
    print(lock.coord._acquired_locks)
    try:
        value = lock.coord.client.get(lock.name)
    except Exception as e:
        return False
    if value != lock.coord._member_id:
        return False
    else:
        was_deleted = lock.coord.client.delete(lock.name,
                                               noreply=False)
        if was_deleted:
            lock.coord._acquired_locks.remove(lock)
        return was_deleted


_acquire()

pdb.set_trace()
_release_1()
# lock.coord.client.delete(lock.name)

# lock.release()

# lock.is_still_owner()

# # lock.coord.client.get(lock.name)
# lock.coord.client.add(lock.name, lock.coord._member_id, expire=30, noreply=False)
# # lock.coord.client.touch(lock.name, expire=LOCK_TIMEOUT)
# # lock.coord.client.set(lock.name, b"It's alive!", expire=LOCK_TIMEOUT)

pdb.set_trace()
coordinator.stop()




# echo "get __TOOZ_LOCK_uuid-delete_snasphot" | nc 10.110.29.1 11212
# kubectl port-forward --address 10.110.29.1 pod/openstack-memcached-memcached-767cf5fbc7-tvrfg 11212:11211 -n openstack
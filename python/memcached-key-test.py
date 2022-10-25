from tooz import coordination
from tooz import _retry
from oslo_utils import timeutils
import uuid
import time
import tenacity
import logging
import threading


LOG = logging.getLogger(__name__)
LOCK_TIMEOUT = 30
url = "memcached://memcached.openstack.svc.region-stackdev.myinspurcloud.com:11211"
#url = "memcached://100.101.89.252:11211"
member_id = ("cinder-" + str(uuid.uuid4())).encode('ascii')
coordinator = coordination.get_coordinator(
    url, member_id, lock_timeout=LOCK_TIMEOUT
)
coordinator.start(start_heart=True)

lock_name = "uuid-delete_snasphot".encode("ascii")

# to produce a dead lock
lock = coordinator.get_lock(lock_name)

res = lock.acquire()
print("acquire lock success: %s", res)

lock.release()
coordinator.stop()

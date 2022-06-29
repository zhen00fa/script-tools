from tooz import coordination
import uuid
import logging
import pdb


LOG = logging.getLogger(__name__)


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

lock.acquire()

print("请立即中断port forward")
pdb.set_trace()

try:
    lock.release()
except Exception as e:
    pass

print("请立即恢复port forward")
pdb.set_trace()
coordinator.stop()

# echo "get __TOOZ_LOCK_uuid-delete_snasphot" | nc 10.110.29.1 11212
# kubectl port-forward --address 10.110.29.1 pod/openstack-memcached-memcached-767cf5fbc7-tvrfg 11212:11211 -n openstack

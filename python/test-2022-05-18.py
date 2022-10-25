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



from six.moves import urllib
import hashlib
from oslo_utils import units
from glance_store.common import utils
import os

uri="http://minio.jinan-lab-arm.myinspurcloud.com/ecs/%E5%A4%A7%E9%95%9C%E5%83%8F%E6%B5%8B%E8%AF%95.raw?Content-Disposition=attachment%3B%20filename%3D%22%E5%A4%A7%E9%95%9C%E5%83%8F%E6%B5%8B%E8%AF%95.raw%22&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=admin%2F20220915%2F%2Fs3%2Faws4_request&X-Amz-Date=20220915T025021Z&X-Amz-Expires=432000&X-Amz-SignedHeaders=host&X-Amz-Signature=a6944a94856e85e227b282224bf6157d0116d75a9669eee369bfac9b0c43e8e5"

data=urllib.request.urlopen(uri)
print(data.headers['content-length'])

hashing_algo = "md5"

bytes_written = 0
os_hash_value = hashlib.new(str(hashing_algo))
checksum = hashlib.md5()
bytes_written = 0
filepath = "/tmp/staging/test_image"
image_file = data
WRITE_CHUNKSIZE = 64 * units.Ki

with open(filepath, 'wb') as f:
    for buf in utils.chunkreadable(image_file,
                                   WRITE_CHUNKSIZE):
        bytes_written += len(buf)
        os_hash_value.update(buf)
        checksum.update(buf)
        f.write(buf)

# new
from six.moves import urllib
import hashlib
from oslo_utils import units
from glance_store.common import utils
import os
import mmap

uri="http://minio.jinan-lab-arm.myinspurcloud.com/ecs/%E5%A4%A7%E9%95%9C%E5%83%8F%E6%B5%8B%E8%AF%95.raw?Content-Disposition=attachment%3B%20filename%3D%22%E5%A4%A7%E9%95%9C%E5%83%8F%E6%B5%8B%E8%AF%95.raw%22&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=admin%2F20220915%2F%2Fs3%2Faws4_request&X-Amz-Date=20220915T025021Z&X-Amz-Expires=432000&X-Amz-SignedHeaders=host&X-Amz-Signature=a6944a94856e85e227b282224bf6157d0116d75a9669eee369bfac9b0c43e8e5"

data=urllib.request.urlopen(uri)
print(data.headers['content-length'])

hashing_algo = "md5"

bytes_written = 0
os_hash_value = hashlib.new(str(hashing_algo))
checksum = hashlib.md5()
bytes_written = 0
filepath = '/tmp/staging/test_image'
image_file = data
WRITE_CHUNKSIZE = 64 * units.Ki

fd = os.open(filepath, (os.O_RDWR | os.O_CREAT | os.O_DIRECT))
m = mmap.mmap(-1, WRITE_CHUNKSIZE)
for buf in utils.chunkreadable(image_file,
                               WRITE_CHUNKSIZE):
    m.seek(0)
    bytes_written += len(buf)
    os_hash_value.update(buf)
    checksum.update(buf)
    m.write(buf)
    os.write(fd, m)
os.close(fd)


#!/usr/bin/python

import os, sys, mmap

# Open a file
fd = os.open( "foo.txt", os.O_RDWR|os.O_CREAT|os.O_DIRECT)
m = mmap.mmap(-1, 1024)
s = ' ' * 1024
m.write(s)
# Write one string
os.write(fd, m)
# Close opened file
os.close(fd)


#!/usr/bin/env python
import os, sys, mmap


size = 1024 * 1024
with open('/tmp/test1', 'rb') as f:
    fd = os.open('/tmp/test2', os.O_RDWR | os.O_CREAT | os.O_DIRECT)
    m = mmap.mmap(-1, size)
    while True:
        m.seek(0)
        buf = f.read(size)
        print(len(buf))
        if not buf:
            break
        m.write(buf)
        os.write(fd, m)
    os.close(fd)






import eventlet

def handle(client):
    while True:
        c = client.recv(1)
        if not c: break
        client.sendall(c)


server = eventlet.listen(('0.0.0.0', 6000))
pool = eventlet.GreenPool(10000)
while True:
    new_sock, address = server.accept()
    pool.spawn_n(handle, new_sock)

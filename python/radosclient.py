import rados, sys
import rbd

cluster = rados.Rados(conffile='/etc/ceph/ceph.conf')
print "\nlibrados version: " + str(cluster.version())
print "Will attempt to connect to: " + str(cluster.conf_get('mon initial members'))
cluster.connect()
print "\nCluster ID: " + cluster.get_fsid()
try:
    ioctx = cluster.open_ioctx('cinder.volumes')
    try:
#        rbd_inst = rbd.RBD()
#        size = 4 * 1024**3  # 4 GiB
#        rbd_inst.create(ioctx, 'myimage', size)
        image = rbd.Image(ioctx, 'volume-8b44a7cf-b62f-4a30-8408-0c630d6a4aef')
        try:
#            data = 'foo' * 200
#            image.write(data, 0)
            # print features of image
            features=image.features()
            print(features)
        finally:
            image.close()
    finally:
        ioctx.close()
finally:
    cluster.shutdown()

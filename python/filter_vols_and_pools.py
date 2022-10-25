import sys
import socket
import json
from cinder import version
from oslo_config import cfg
from cinder import context as cinder_context
from cinder import objects
objects.register_all()
from cinder.cmd.volume import host_opt
from cinder import rpc
from cinder.scheduler.host_manager import HostManager
from cinder.common import constants
from cinder.volume import API
from cinder import volume as cinder_volume
CONF = cfg.CONF


def init_app():
    """initialize application"""

    cfg.CONF(
        sys.argv[1:],
        project='cinder',
        version=version.version_string()
    )

    # choose the first in backend list
    backend = cfg.CONF.enabled_backends[0]
    cfg.CONF.register_opt(
        host_opt,
        backend
    )

    # get backend host
    backend_host = getattr(
        cfg.CONF,
        backend
    ).backend_host

    if not backend_host:
        backend_host = socket.gethostname()

    # form a host
    host = "%s@%s" % (
        backend_host,
        backend
    )

    rpc.init(cfg.CONF)

    return (
        backend, host, None
    )


def save_files(file, path, mode='w'):
    with open(path, mode) as f:
        f.write(file)


def get_attach_info(vol_obj):
    attach_info = ""
    attach_list = vol_obj.volume_attachment
    if attach_list:
        for attach in attach_list:
            if attach.instance_uuid and attach.mountpoint:
                attach_info = attach_info + str(attach.instance_uuid) + ":" + " " + str(attach.mountpoint) + " "
    return attach_info


def get_tgt_snapshot(ctx, vol_obj):
    snapshot_ids = ""
    snapshot_objs = objects.SnapshotList.get_all_for_volume(ctx, vol_obj.id)
    if snapshot_objs:
        for snapshot_obj in snapshot_objs:
            if snapshot_obj.id:
                snapshot_ids = snapshot_ids + str(snapshot_obj.id) + ";"
    return snapshot_ids


def load_form(ctx, vol_obj):
    return {
        "volume_id": vol_obj.id,
        "name": vol_obj.name,
        "volume_type": vol_obj.volume_type_id, "src_snapshot_id": vol_obj.snapshot_id,
        "status": vol_obj.status, "size": vol_obj.size,
        "project_id": vol_obj.project_id, "bootable": vol_obj.bootable,
        "attach_info": get_attach_info(vol_obj),
        "tgt_snapshot_id": get_tgt_snapshot(ctx, vol_obj)
    }


def main():
    volume_type_ids = {
        "c1e33b91-beeb-41af-8f70-3e7693602d50",
        "1a13b512-d39c-42b8-ae85-8c5b779bee6e",
        "85711798-3808-4c85-8cc3-9d8838e7108b"
        # "92b5230d-f13c-4499-8a34-87a26fda3ce2"
    }
    host_list = {}
    ctx = cinder_context.get_admin_context()
    # hm = HostManager()
    # pool_details = hm.get_pools(ctx, filters={})
    # print(str(pool_details))
    for vol_type in volume_type_ids:
        volume_objs = objects.VolumeList.get_all(
            ctx, filters={"volume_type_id": vol_type}
        )
        for vol_obj in volume_objs:
            if vol_obj.host not in host_list:
                host_list[vol_obj.host] = [load_form(ctx, vol_obj)]
            else:
                host_list[vol_obj.host].append(load_form(ctx, vol_obj))
    if host_list:
        j = json.dumps(host_list)
        print(str(j))
        save_files(str(j), '/tmp/host_list', 'w')


if __name__ == "__main__":
    init_app()
    main()

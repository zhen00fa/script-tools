import xlwt
import json


OUTPUT_FILE = "vols.xls"
tittles = ["volume_id", "name", "volume_type", "src_snapshot_id", "status", "size", "project_id", "bootable", "attach_info", "tgt_snapshot_id"]


def load_from_file(path):
    with open(path, 'r') as jsonfile:
        host_list = json.load(jsonfile)
    return host_list


def write_to_excel(host_list={}):
    print("write flavors to excel file:" + OUTPUT_FILE)
    workboot = xlwt.Workbook()
    for host, vol_obj in host_list.items():
        wsheet = workboot.add_sheet(host.split("@", 1)[0])
        # write tittles
        for i in range(len(tittles)):
            wsheet.write(0, i, tittles[i])
        # write volume info
        write_row = 1
        for vol in vol_obj:
            volume_id = vol.get("volume_id")
            name = vol.get("name")
            volume_type = vol.get("volume_type")
            src_snapshot_id = vol.get("src_snapshot_id")
            status = vol.get("status")
            size = vol.get("size")
            project_id = vol.get("project_id")
            bootable = vol.get("bootable")
            attach_info = vol.get("attach_info")
            tgt_snapshot_id = vol.get("tgt_snapshot_id")
            data = [volume_id, name, volume_type, src_snapshot_id, status, size, project_id, bootable, attach_info, tgt_snapshot_id]
            for j in range(len(data)):
                wsheet.write(write_row, j, data[j])
            write_row = write_row + 1
    workboot.save(OUTPUT_FILE)


def main():
    volumelist = load_from_file("/tmp/vol_list")
    write_to_excel(volumelist)


if __name__ == "__main__":
    main()

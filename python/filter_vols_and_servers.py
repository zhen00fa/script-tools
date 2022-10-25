import xlwt
import json

from keystoneauth1 import loading, session
from novaclient import client # require version >= 10.0.0
from cinderclient.v3 import client as clientc
from keystoneclient.v3 import client as kclient

# environment configuration
AUTH_URL = 'http://keystone.openstack.svc.cn-north-3.myinspurcloud.com/v3'
USERNAME = 'admin'
PASSWORD = '0gG9SMvrC5RuuvJc'
PROJECT_NAME = 'admin'
DOMAIN_NAME = 'Default'
NOVACLIENT_VERSION = 2.65
CINDERCLIENT_VERSION = 3.50


OUTPUT_FILE = "/tmp/server_list.xls"
rds_local_aggregate = "cn-north-3a_rds-mysql-local_general"
ecs_local_aggregate = "cn-north-3a_ecs_local-disk1"
ecs_local_hosts = ("cmp350", "cmp351", "cmp352", "cmp353", "cmp354", "cmp355", "cmp356", "cmp357", "cmp358", "cmp359", "compute360", "cmp361", "cmp362", "cmp363", "cmp365", "cmp366", "compute367",)
LVM_TYPE_IDS = {
        "ECS_DISK1": "c1e33b91-beeb-41af-8f70-3e7693602d50",
        "NEWSQL_LOCAL_SSD": "1a13b512-d39c-42b8-ae85-8c5b779bee6e",
        "RDS_LOCAL_SSD": "85711798-3808-4c85-8cc3-9d8838e7108b"
    }
tittles = ["server_id", "server_name", "status", "flavor", "project_id", "project_name", "create_at", "image", "attachment_volumes"]


def get_nova_client(version):
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=AUTH_URL,
                                    username=USERNAME,
                                    password=PASSWORD,
                                    project_name=PROJECT_NAME,
                                    user_domain_name=DOMAIN_NAME,
                                    project_domain_name=DOMAIN_NAME)
    sess = session.Session(auth=auth, verify=False)
    return client.Client(version, session=sess, endpoint_type='internal')


def get_cinder_client(version):
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=AUTH_URL,
                                    username=USERNAME,
                                    password=PASSWORD,
                                    project_name=PROJECT_NAME,
                                    user_domain_name=DOMAIN_NAME,
                                    project_domain_name=DOMAIN_NAME)
    sess = session.Session(auth=auth)
    return clientc.Client(version, session=sess, endpoint_type='internal')


def get_keystone_client():
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=AUTH_URL,
                                    username=USERNAME,
                                    password=PASSWORD,
                                    project_name=PROJECT_NAME,
                                    user_domain_name=DOMAIN_NAME,
                                    project_domain_name=DOMAIN_NAME)
    sess = session.Session(auth=auth)
    return kclient.Client(session=sess)


client = get_nova_client(version=NOVACLIENT_VERSION)
cinder_client = get_cinder_client(version=CINDERCLIENT_VERSION)
keystone_client = get_keystone_client()


def get_project_name(project_id):
    project = keystone_client.projects.get(project_id)
    return project.name


def get_image_name(server_obj):
    image_ref = server_obj.image
    if image_ref:
        return image_ref.get('id')
    else:
        return None


def load_form(server_obj):
    attachs = server_obj.__dict__['os-extended-volumes:volumes_attached']
    volumes = []
    if attachs:
        volumes = [attach.get("id") for attach in attachs]
    return {
        "server_id": str(server_obj.id),
        "server_name": str(server_obj.name),
        "status": str(server_obj.status),
        "flavor": str(server_obj.flavor.get('original_name')),
        "project_id": str(server_obj.tenant_id),
        "project_name": get_project_name(server_obj.tenant_id),
        "create_at": server_obj.created,
        "image": get_image_name(server_obj),
        "attachment_volumes": str(volumes)
    }


def list_host_servers(host):
    """get all servers on the host and check servers status"""

    server_list = []
    servers = client.servers.list(
        search_opts={'host': host, 'all_tenants': True}
    )

    for server in servers:
        server_list.append(load_form(server))

    return server_list


def save_files(file, path, mode='w'):
    with open(path, mode) as f:
        f.write(file)


def load_from_file(path):
    with open(path, 'r') as jsonfile:
        host_list = json.load(jsonfile)
    return host_list


def write_to_excel(servers):
    print("write flavors to excel file:" + OUTPUT_FILE)
    workboot = xlwt.Workbook()
    for host, server_obj in servers.items():
        wsheet = workboot.add_sheet(host.split("@", 1)[0])
        # write tittles
        for i in range(len(tittles)):
            wsheet.write(0, i, tittles[i])
        # write volume info
        write_row = 1
        for server in server_obj:
            server_id = server.get("server_id")
            server_name = server.get("server_name")
            status = server.get("status")
            flavor = server.get("flavor")
            project_id = server.get("project_id")
            project_name = server.get("project_name")
            create_at = server.get("create_at")
            image = server.get("image")
            attachment_volumes = server.get("attachment_volumes")
            data = [server_id, server_name, status, flavor, project_id, project_name, create_at, image, attachment_volumes]
            for j in range(len(data)):
                wsheet.write(write_row, j, data[j])
            write_row = write_row + 1
    workboot.save(OUTPUT_FILE)


def get_hosts():
    ecs_local_hosts = client.aggregates.get(ecs_local_aggregate).hosts
    rds_local_hosts = client.aggregates.get(rds_local_aggregate).hosts
    return set(ecs_local_hosts) & set(rds_local_hosts)


def main():
    servers = {}
    hosts = get_hosts()
    for host in hosts:
        servers[host] = list_host_servers(host)
    if servers:
        write_to_excel(servers)


if __name__ == '__main__':
    main()

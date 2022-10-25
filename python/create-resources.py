import fcntl
import random
import string
from keystoneauth1 import loading, session
from novaclient import client # require version >= 10.0.0
from keystoneclient.v3 import client as kclient
from neutronclient.v2_0 import client as neutronc
from concurrent.futures import FIRST_COMPLETED, ALL_COMPLETED, FIRST_EXCEPTION
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
import time
import os


# environment configuration
AUTH_URL = 'http://keystone-api.openstack.svc.region-x86-large.myinspurcloud.com:5000/v3'
USERNAME = 'admin'
PASSWORD = 'l141tRm8K9CmFX4A'
PROJECT_NAME = 'admin'
DOMAIN_NAME = 'Default'
NOVACLIENT_VERSION = 2.1
CINDERCLIENT_VERSION = 3.50

huge_vpc1 = "044b9b9e-cc9e-4bf6-aeda-a7712f9d4a48"
huge_vpc2 = "b6a9df07-6f60-4564-bd15-2347754dd709"

floating = "2c8b918f-d37c-4dcd-adde-387e72375963"
service_data = "82d7616b-5fe6-4ad3-9b1e-fcce95590c2e"

flavor = "ac76bd84-132b-4ae9-89d0-3ea6e226187a"
image = "81a8cb3b-a382-443d-945e-98c9cc283c4a"


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


def get_neutron_client():
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=AUTH_URL,
                                    username=USERNAME,
                                    password=PASSWORD,
                                    project_name=PROJECT_NAME,
                                    user_domain_name=DOMAIN_NAME,
                                    project_domain_name=DOMAIN_NAME)
    sess = session.Session(auth=auth)
    return neutronc.Client(session=sess, endpoint_type='internal')


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


nova_client = get_nova_client(version=NOVACLIENT_VERSION)
neutron_client = get_neutron_client()
keystone_client = get_keystone_client()


def read_file(path):
    with open(path, 'r') as f:
        lines = f.readlines()
        dict_tag_list = []
        for line in lines:
            line = line.strip('\n')
            dict_tag_list.append(line)
    return dict_tag_list


def write_to_file(content, file):
    with open(file, encoding='utf-8', mode='a') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(content + '\n')


def get_network(project):
    #project_id = get_project_name(project)
    network = neutron_client.list_networks(tenant_id=project)
    return network.get("networks")[0].get("id")


def get_router(project):
    routers = neutron_client.list_routers(tenant_id=project)
    return routers.get("routers")[0].get("id")


def wait_for_server_status(server_id, timeout=400, interval=5):
    start_time = time.time()
    while time.time() - start_time < timeout:
        print("waiting stats for server:", server_id)
        server_obj = nova_client.servers.get(server_id)
        if server_obj.status == "ACTIVE":
            print("server %s create success", server_id)
            break
        if server_obj.status == "ERROR":
            print("server %s create failed", server_id)
            server_obj.delete()
            raise Exception
        time.sleep(interval)
    else:
        print("server %s did not reach status success after %d seconds.", server_id, timeout)
        server_obj.force_delete()
        raise Exception

# def get_project_name(project_id):
#     project = keystone_client.projects.get(project_id)
#     return project.name


def create_port(network_id):
    name = 'lz-test-' + ''.join(random.sample(string.ascii_letters + string.digits, 6))
    body = {
        "port": {
            'network_id': network_id,
            'name': name
        }
    }
    port = neutron_client.create_port(body).get('port')
    port_id = port.get('id')


def create_floatingipaddr(network_id, port_id):
    body = {
        "floatingip": {
            'floating_network_id': network_id,
            'port_id': port_id
        }
    }
    fip = neutron_client.create_floatingip(body).get('floatingip')
    fip_address = fip.get('floating_ip_address')
    fip_id = fip.get('id')
    print('The new floating ip created: %s' % fip_address)
    return fip_address, fip_id


def main():
    all_hosts = read_file("/home/lz/create_servers/hosts")
    used_hosts = read_file("/home/lz/create_servers/used_hosts")
    hosts = list(set(all_hosts) - set(used_hosts))
    all_projects = read_file("/home/lz/create_servers/projects")
    for host in hosts:
        name = 'lz-test-' + ''.join(random.sample(string.ascii_letters + string.digits, 8))
        print("start create server on " + host)
        az = ":" + host
        used_pj = read_file("/home/lz/create_servers/used_projects")
        projects = list(set(all_projects) - set(used_pj))
        tmpl = [{'net-id': huge_vpc1}, {'net-id': huge_vpc2}]
        used_projects = []
        used_nets = []
        # for i in range(4):
        #     print(projects[i])
        #     if i == 0:
        #         try:
        #             router = get_router(projects[i])
        #             if router:
        #                 neutron_client.add_gateway_router(router, {'network_id': floating})
        #         except Exception as e:
        #             print("add external gateway for router failed in project " + projects[i])
        #             print("error message:", e)
        #             pass
        #     network_id = get_network(projects[i])
        #     tmpl.append({'net-id': network_id})
        #     used_projects.append(projects[i])
        #     used_nets.append(network_id)

        server = nova_client.servers.create(name=name, flavor=flavor, image=image, nics=tmpl, availability_zone=az)
        try:
            wait_for_server_status(server.id)
        except Exception:
            continue

        write_to_file(server.id, "/home/lz/create_servers/servers")
        # add floating ip
        print("add fips")
        try:
            port_list = server.interface_list()
            for port_obj in port_list:
                if port_obj.net_id == huge_vpc1:
                    create_floatingipaddr(floating, port_obj.port_id)
                if port_obj.net_id == huge_vpc2:
                    create_floatingipaddr(service_data, port_obj.port_id)
                if port_obj.net_id == used_nets[0]:
                    create_floatingipaddr(floating, port_obj.port_id)
        except Exception as e:
            print("add floating ip error: %s", e)
        # soft reboot
        print("reboot server", server.id)
        server.reboot()

        write_to_file(host, "/home/lz/create_servers/used_hosts")
        for pj in used_projects:
            write_to_file(pj, "/home/lz/create_servers/used_projects")


if __name__ == '__main__':
    main()

#!/bin/bash

set -ex

# create floating
#openstack network create --provider-physical-network physnet1 --provider-network-type vlan --provider-segment 832 --external --share floating
#openstack subnet create --network 2c8b918f-d37c-4dcd-adde-387e72375963 --gateway 100.162.255.254 --subnet-range 100.162.0.0/16 --allocation-pool start=100.162.0.1,end=100.162.255.251 sub_floating

# create service_data
# openstack network create --provider-physical-network physnet1 --provider-network-type vlan --provider-segment 831 --external --share service_data
# openstack subnet create --network service_data --gateway 100.161.255.254 --subnet-range 100.161.0.0/16 --allocation-pool start=100.161.0.1,end=100.161.255.251 sub_service_data

# create huge vpc 1
openstack network show huge-vpc1 || openstack network create --project admin --share huge-vpc1
for i in {1..70}; do
  openstack subnet  create  --project admin --subnet-range 10.221.${i}.0/24 --network huge-vpc1  sub-huge-vpc1-${i}
done

# create huge vpc 2
openstack network show huge-vpc2 || openstack network create --project admin --share huge-vpc2
for i in {1..70}; do
  # for i in {1..70}; do openstack subnet  create  --project admin --subnet-range 10.221.${i}.0/24 --network huge-vpc2  sub-huge-vpc2-${i}; done
  openstack subnet  create  --project admin --subnet-range 10.221.${i}.0/24 --network huge-vpc2  sub-huge-vpc2-${i}
done

# create networks
for i in {1..70}; do
  openstack network create --project admin --share lz-test-network-${i}
  openstack subnet  create  --project admin --subnet-range 10.221.${i}.0/24 --network lz-test-network-${i}  sub-test-network-${i}
done

# create huge router 1
router_ID=$(openstack router create --project admin  huge-router-1 -c id -f value)
openstack router set --external-gateway floating huge-router-1
for i in {1..70}; do
  echo "add subnet sub-huge-vpc1-${i}"
  openstack router add subnet huge-router-1 sub-huge-vpc1-${i}
done


# create huge router 2
router_ID=$(openstack router create --project admin  huge-router-2 -c id -f value)
openstack router set --external-gateway service_data huge-router-2
for i in {1..70}; do
  echo "add subnet sub-huge-vpc2-${i}"
  openstack router add subnet huge-router-2 sub-huge-vpc2-${i}
done


# create project and resources
function create_networks() {
  local index_a
  local index_b
  for i in {index_a..index_b};do
    openstack project create --or-show project-${i}
    # create network
    echo "create network"
    net_ID=$(openstack network create --project project-${i} Default-vpc -c id -f value)
    subnet_ID=$(openstack subnet create --project project-${i} --subnet-range 172.31.0.0/20 --network ${net_ID} Default-subnet -c id -f value)
    openstack port create --network ${net_ID} test-unbond --project project-${i}

    # create router
    echo "create router"
    router_ID=$(openstack router create --project project-${i} test-router -c id -f value)
    openstack router add subnet ${router_ID} ${subnet_ID}
    if [ ${i} -le "100" ]; then
      openstack router set ${router_ID} --route destination=192.168.0.0/16,gateway=172.31.0.8
    fi

    # create rule for security group
    echo "create rules and security group"
    sg_ID=$(openstack security group list --project project-${i} -f value |grep default |head -n 1 |awk '{print $1}')
    openstack security group rule create --ingress --protocol tcp --dst-port 117:126 --project project-${i} ${sg_ID}
    openstack security group rule create --ingress --protocol tcp --dst-port 127:136 --project project-${i} ${sg_ID}
    openstack security group rule create --ingress --protocol tcp --dst-port 137:146 --project project-${i} ${sg_ID}
    openstack security group rule create --ingress --protocol tcp --dst-port 147:156 --project project-${i} ${sg_ID}
    openstack security group rule create --ingress --protocol tcp --dst-port 157:166 --project project-${i} ${sg_ID}
    openstack security group rule create --ingress --protocol tcp --dst-port 167:176 --project project-${i} ${sg_ID}
    openstack security group rule create --ingress --protocol tcp --dst-port 177:186 --project project-${i} ${sg_ID}
    openstack security group rule create --ingress --protocol tcp --dst-port 187:196 --project project-${i} ${sg_ID}
    openstack security group rule create --ingress --protocol tcp --dst-port 197:206 --project project-${i} ${sg_ID}
    openstack security group rule create --ingress --protocol tcp --dst-port 207:216 --project project-${i} ${sg_ID}
    # create security group
    openstack security group create --project project-${i} sg-test
  done
}


function retry() {
   for x in $(seq 1 3); do
      [ $x -gt 1 ] && echo "WARNING: cmd executeion failed, will retry in $x times later" && sleep 2
      cmd ${x} && r=0 && break || r=$?
   done

   #OTHER COMMANDS

   return $r
}

for i in {1..7500}; do
  openstack project create --or-show project-${i}
  # create network
  echo "create network"
  net_ID=$(openstack network create --project project-${i} Default-vpc -c id -f value)
  subnet_ID=$(openstack subnet create --project project-${i} --subnet-range 172.31.0.0/20 --network ${net_ID} Default-subnet -c id -f value)
  openstack port create --network ${net_ID} test-unbond --project project-${i}

  # create router
  echo "create router"
  router_ID=$(openstack router create --project project-${i} test-router -c id -f value)
  openstack router add subnet ${router_ID} ${subnet_ID}
  if [ ${i} -le "100" ]; then
    openstack router set ${router_ID} --route destination=192.168.0.0/16,gateway=172.31.0.8
  fi

  # create rule for security group
  echo "create rules and security group"
  sg_ID=$(openstack security group list --project project-${i} -f value |grep default |head -n 1 |awk '{print $1}')
  openstack security group rule create --ingress --protocol tcp --dst-port 117:126 --project project-${i} ${sg_ID}
  openstack security group rule create --ingress --protocol tcp --dst-port 127:136 --project project-${i} ${sg_ID}
  openstack security group rule create --ingress --protocol tcp --dst-port 137:146 --project project-${i} ${sg_ID}
  openstack security group rule create --ingress --protocol tcp --dst-port 147:156 --project project-${i} ${sg_ID}
  openstack security group rule create --ingress --protocol tcp --dst-port 157:166 --project project-${i} ${sg_ID}
  openstack security group rule create --ingress --protocol tcp --dst-port 167:176 --project project-${i} ${sg_ID}
  openstack security group rule create --ingress --protocol tcp --dst-port 177:186 --project project-${i} ${sg_ID}
  openstack security group rule create --ingress --protocol tcp --dst-port 187:196 --project project-${i} ${sg_ID}
  openstack security group rule create --ingress --protocol tcp --dst-port 197:206 --project project-${i} ${sg_ID}
  openstack security group rule create --ingress --protocol tcp --dst-port 207:216 --project project-${i} ${sg_ID}
  # create security group
  openstack security group create --project project-${i} sg-test
done


# create server
host_list=$(openstack compute service list --service nova-compute -f value |grep enabled |grep up |awk '{print $3}')
for i in ${host_list}; do

  echo $i

  nova boot --nic none --image bcb9dd82-4e83-4ed5-afe4-929c558bca61 --flavor ac76bd84-132b-4ae9-89d0-3ea6e226187a --availability-zone :$i test-$i-1

done

openstack server create


for server in $(cat /tmp/tmp_servers); do
  huge_PORT1=$(openstack port create --network huge-vpc1 test-huge1-${server:0:4} -f value -c id)
  openstack floating ip create  floating --port $huge_PORT1
  openstack server add port $server $huge_PORT1
  huge_PORT2=$(openstack port create --network huge-vpc2 test-huge2-${server:0:4} -f value -c id)
  openstack floating ip create  service_data --port $huge_PORT2
  openstack server add port $server $huge_PORT2
#  openstack server rebuild $server --image 81a8cb3b-a382-443d-945e-98c9cc283c4a
  echo "asasd" >> done_servers
done


# nohup create.sh > out.log
# nohup bash create_1-100.sh > create_1-100.log 2>&1 &



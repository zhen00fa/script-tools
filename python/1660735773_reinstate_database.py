#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''
Reinstate instances or volumes which are in abnormal states
for ICP platform.
'''

import os
import logging
import json
import re
import subprocess
import sys
import codecs
import configparser
import pdb

logging.basicConfig(filename='/var/log/reinstate_health.log',
                    format='%(asctime)s %(name)s: %(levelname)s %(message)s',
                    level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')

# To be able to recognize chinese. However, print will not output its contents when this script exits.
# Therefore. substitute subprocess.call for print function.
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())


def execute_openstack_cmd(command):
    """
    No matter whether openstack client is containerized,
    it's able to issue openstack commands successfully.

    :param command: concrete openstack command.
    :return: 0 is indicative of failure.
    """

    os_prefix = ''
    res1 = os.popen('which openstack').readlines()
    if len(res1) > 0 and 'openstack' in res1[0].strip():
        os_prefix = '. /root/openrc;'
    else:
        img_search = os.popen(
            "docker images|grep openstackclient|awk 'NR==1 {print $3}'").readlines()
        if len(img_search) == 1:
            img_id = img_search[0].strip()
        else:
            logging.warning('Please prepare containerized image of openstackclient'
                            ' in order to be able to use this script!')
            return 0
        os_prefix = 'docker run -i --rm --env-file /opt/openrc --network host ' + img_id + ' '
    res2 = subprocess.Popen(os_prefix + command, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                            encoding='utf8').stdout.readlines()
    if 'res2' in locals().keys():
        return res2
    else:
        logging.error('Fail to execute %s' % command)
        return 0


def get_instance_info(instance_id):
    """
    Retrieve some desired information about instance.

    :param instance_id: uuid of instance.
    :return: desired information about instance.
    """

    info = {}
    cmd = 'openstack server show ' + instance_id + ' -f value -c OS-EXT-SRV-ATTR:host ' \
                                                   '-c OS-EXT-SRV-ATTR:hypervisor_hostname ' \
                                                   '-c OS-EXT-SRV-ATTR:instance_name ' \
                                                   '-c volumes_attached'
    res = execute_openstack_cmd(cmd)
    hostname = res[0].strip()
    hypervisor_hostname = res[1].strip()
    instance_name = res[2].strip()
    volume_attached = []
    for i in range(3, len(res)):
        # e.g. id='8a68da93-c95b-4f1b-9516-651f16294c20' of strip()[3:] is '8a68da93-c95b-4f1b-9516-651f16294c20'
        volume_attached.append(res[i].strip()[3:].strip("'"))
    info['hostname'] = hostname
    info['hypervisor_hostname'] = hypervisor_hostname
    info['instance_name'] = instance_name
    info['volume_attached'] = volume_attached
    logging.info('The info of instance %s is %s.' % (instance_id, info))

    return info


def get_volume_info(volume_id):
    """
    Retrieve some desired information about volume.

    :param volume_id: uuid of volume.
    :return: desired information about volume.
    """

    info = {}
    cmd = 'openstack volume show ' + volume_id + ' -f value -c attachments ' \
                                                 '-c multiattach ' \
                                                 '-c name ' \
                                                 '-c os-vol-host-attr:host ' \
                                                 '-c os-vol-mig-status-attr:name_id ' \
                                                 '-c type'
    res = execute_openstack_cmd(cmd)
    attachments = res[0].strip()
    attachments_json = attachments.strip('[').strip(']').replace(
        "'", "\"").replace("u\"", "\"").replace('None', 'null')
    # Cannot retrieve server_id and device for volume supporting multiattach
    if bool(attachments_json) is True and len(attachments_json.split('}, ')) == 1:
        device = json.loads(attachments_json)['device']
        server_id = json.loads(attachments_json)['server_id']
        host_name = json.loads(attachments_json)['host_name']
    else:
        device = None
        server_id = None

        host_name = None
    multiattach = res[1].strip()
    if multiattach == 'False':
        logging.info('The volume %s does not support multiattach!' % volume_id)
    else:
        logging.info('The volume %s supports multiattach!' % volume_id)
    name = res[2].strip()
    vol_host = res[3].strip()
    vol_name_id = res[4].strip()
    type = res[5].strip()
    if type != 'None':
        cmd = 'openstack volume type show ' + type + ' -f value -c id'
        type_id = execute_openstack_cmd(cmd)[0].strip()
    else:
        type_id = None
        logging.warning('The type of volume %s is None!' % volume_id)
    info['attachments'] = attachments
    info['multiattach'] = multiattach
    info['name'] = name
    info['vol_host'] = vol_host
    info['vol_name_id'] = vol_name_id
    info['type'] = type
    info['type_id'] = type_id
    info['device'] = device
    info['server_id'] = server_id
    info['host_name'] = host_name
    logging.info('The info of volume %s is %s' % (volume_id, info))

    return info


def get_block_info(volume_id):
    """
    Retrieve block information by qemu-monitor-command of vrish and guarantee blockjob has finished.
    For example, the format of ceph volume is
    libvirt-1-format: json:{"driver": "raw", "file": {"pool": "cinder.volumes_ssd",
    "image": "volume-7cff8253-11aa-4ffe-b243-9ea3b053f173", "server.0.host": "100.200.2.76",
    "server.1.host": "100.200.2.78", "server.2.host": "100.200.2.77", "driver": "rbd",
    "server.0.port": "6789", "server.1.port": "6789", "server.2.port": "6789",
    "user": "cinder_5e7db6d4-e957-4036-817f-cb57ff70e12c"}} (raw)

    And the format of Fibre channel volume is
    libvirt-2-format: /dev/disk/by-id/dm-uuid-mpath-3600000e00d2a0000002a09ee00870000 (raw)

    And the format of LVM volume is
    libvirt-1-format: /dev/sdc (raw)

    :param instace_id: uuid of instance.
    :param volume_id: uuid of volume.
    :return: block information in terms of qemu or 0 is indicative of failing to retrieve block information.
    """

    volume_info = get_volume_info(volume_id)
    instance_id = volume_info['server_id']
    instance_info = get_instance_info(instance_id)
    hostname = instance_info['hostname']
    instance_name = instance_info['instance_name']

    # get libvirt pod
    cmd = "kubectl get pod -n openstack -owide | grep -i libvirt | grep -i " + hostname \
          + " | awk '{print $1}'"
    libvirt_pod = os.popen(cmd).readlines()[0].strip()

    # enter libvirt pod and retrieve block information
    cmd = "kubectl exec -it -n openstack " + \
          libvirt_pod + " -- virsh domstate " + instance_name
    if os.popen(cmd).readlines()[0].strip() == 'shut off':
        blk_info = None
        logging.info(
            'The instance %s is stopped in terms of libvirt.' % instance_id)
    else:
        device = volume_info['device']
        if device is None:
            blk_info = None
            logging.info('Fail to get block info since device is None.')
            return 0

        # Guarantee blockjob has finished
        # e.g. '/dev/vdd'[5:] is vdd
        disk = device[5:]
        cmd1 = "kubectl exec -it -n openstack " + libvirt_pod + " -- virsh blockjob " \
               + instance_name + " " + disk
        blk_job = os.popen(cmd1).readlines()[0].strip()
        if 'No current block job for %s' % disk not in blk_job:
            logging.warning('There is a block job for %s or an error which is %s encountered '
                            'when query block job!' % (volume_id, blk_job))
            return 0
        logging.info('The block job for %s has finished, i.e., %s!' %
                     (volume_id, blk_job))

        # e.g. '/dev/vdd'[7:] is d
        device_index = str(ord(device[7:]) - ord('a'))
        # disk identifiers in libvirt are in order, i.e., vda, vdb etc. However, they are not
        # sequential in qemu and real block info can be identified by virtio-disk number.
        cmd2 = "kubectl exec -it -n openstack " + libvirt_pod + " -- virsh qemu-monitor-command --hmp " \
               + instance_name + \
               " info block | grep -B 1 'peripheral/virtio-disk" + device_index + "' | grep -iv attach"
        blk_info = os.popen(cmd2).readlines()[0].strip()
        logging.info('The block information of device %s of instance %s in terms of qemu is %s.'
                     % (device, instance_id, blk_info))
    return blk_info


def get_connection_info(volume_id):
    '''
    Get connection info from cinder and nova for a volume.

    :param volume_id: uuid of volume.
    :return: attachment_id of connection info or zero
             which is indicative of failing to revise connection info.
    '''

    # get attachment in nova.bdm
    var = 'echo ' + volume_id + ' >/tmp/volume_id;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
    sql_statement = '''"SELECT * FROM nova.block_device_mapping WHERE volume_id=\\'${volume_id}\\' and deleted=0\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    pipe = " | grep -i attachment_id | sed 's/attachment_id: //'"
    res = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                           stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    # substitute subprocess.call for print function.
    subprocess.call("echo connection info in nova database is:",
                    shell=True, executable='/bin/bash')
    subprocess.call(cmd, shell=True, executable='/bin/bash')
    if len(res) == 1 and 'NULL' not in res[0].strip():
        # get attachment in cinder with same attachment_id as the nova
        attachment_id = res[0].strip()
        var = 'echo ' + attachment_id + ' >/tmp/attachment_id;'
        var_transfer = '''attachment_id=`cat /tmp/attachment_id`;'''
        sql_statement = '''"SELECT * FROM cinder.volume_attachment WHERE id=\\'${attachment_id}\\'\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        # substitute subprocess.call for print function.
        subprocess.call("echo connection info with attachment_id %s in cinder database is:" %
                        attachment_id, shell=True, executable='/bin/bash')
        subprocess.call(cmd, shell=True, executable='/bin/bash')

        # get attachments in cinder with different attachment_id as the nova
        var = 'echo ' + volume_id + ' >/tmp/volume_id;' + \
              'echo ' + attachment_id + ' >/tmp/attachment_id;'
        var_transfer = '''volume_id=`cat /tmp/volume_id`;''' + \
                       '''attachment_id=`cat /tmp/attachment_id`;'''
        sql_statement = '''"SELECT * FROM cinder.volume_attachment WHERE volume_id=\\'${volume_id}\\' and deleted=0 and id!=\\'${attachment_id}\\'\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        subprocess.call("echo connection info with other attachment_ids in cinder database is:", shell=True,
                        executable='/bin/bash')
        subprocess.call(cmd, shell=True, executable='/bin/bash')
    elif len(res) == 1 and 'NULL' in res[0].strip():
        logging.warning(
            'The attachment id of volume %s in nova is NULL!' % volume_id)
        attachment_id = None
        return 0
    elif len(res) > 1:
        # get attachments in cinder with different attachment_id as the nova
        logging.warning(
            'The attachments of volume %s in nova.bdm are above one!' % volume_id)
        var = 'echo ' + volume_id + ' >/tmp/volume_id;'
        var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
        sql_statement = '''"SELECT * FROM cinder.volume_attachment WHERE volume_id=\\'${volume_id}\\' and deleted=0\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        subprocess.call("echo connection info without specific attachment_id in cinder database is:", shell=True,
                        executable='/bin/bash')
        subprocess.call(cmd, shell=True, executable='/bin/bash')
        return 'many'
    else:
        logging.warning(
            'All attachments in nova of volume %s are deleted or the volume id is invalid' % volume_id)
        attachment_id = None
        return 0

    return attachment_id


def get_storage_info(volume_id):
    '''
    Retrieve storage info for the volume.

    :param volume_id: uuid of volume.
    :return: storage_info for the volume.
    '''

    vol_host = get_volume_info(volume_id)['vol_host']

    # get cinder-volume pod
    cmd = "kubectl  get pod -n openstack -owide | grep cinder-vo | uniq -w 20 | awk '{print $1}'"
    volume_pods = os.popen(cmd).readlines()
    volume_pods = [volume_pod.strip() for volume_pod in volume_pods]

    # inquiry storage information for the volume
    storage_info = {}
    for volume_pod in volume_pods:
        cmd = "kubectl  exec -it -n openstack " + volume_pod + " -- cat /etc/cinder/conf/backends.conf > /root/" + \
              volume_pod + ".ini"
        subprocess.call(cmd, shell=True, executable='/bin/bash')
        # parse config
        conf = configparser.ConfigParser()
        conf.read('/root/' + volume_pod + '.ini')
        if 'cinder_etc_occupy' in conf.sections():
            conf.remove_section('cinder_etc_occupy')
        for section in conf.sections():
            if section in vol_host:
                if 'fujitsu' in conf[section]['volume_driver']:
                    storage_info['volume_driver'] = 'as5600'
                    storage_info['volume_pod'] = volume_pod
                    storage_info['volume_backend_name'] = conf[section]['volume_backend_name']
                    storage_info['cinder_eternus_config_file'] = conf[section]['cinder_eternus_config_file']
                    cmd = "kubectl  exec -it -n openstack " + volume_pod + \
                          " -- cat " + storage_info['cinder_eternus_config_file']
                    pipe = " | grep -vi 'fuji' | grep -v xml | sed 's/<\/E.*//g' | sed 's/<E.*>//g'"
                    res = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                                           encoding='utf8').stdout.readlines()
                    storage_info['EternusIP'] = res[0].strip()
                    storage_info['EternusPort'] = res[1].strip()
                    storage_info['EternusUser'] = res[2].strip()
                    storage_info['EternusPassword'] = res[3].strip()
                    storage_info['EternusPool'] = res[4].strip()
                    storage_info['EternusSnapPool'] = res[5].strip()
                elif 'rbd' in conf[section]['volume_driver']:
                    storage_info['volume_driver'] = 'ceph'
                    storage_info['volume_pod'] = volume_pod
                    storage_info['volume_backend_name'] = conf[section]['volume_backend_name']
                    storage_info['rbd_ceph_conf'] = conf[section]['rbd_ceph_conf']
                    storage_info['rbd_user'] = conf[section]['rbd_user']
                    storage_info['rbd_pool'] = conf[section]['rbd_pool']
                elif 'inspur' in conf[section]['volume_driver']:
                    storage_info['volume_driver'] = 'g2/g5'
                    storage_info['volume_pod'] = volume_pod
                    storage_info['volume_backend_name'] = conf[section]['volume_backend_name']
                    storage_info['instorage_mcs_volpool_name'] = conf[section]['instorage_mcs_volpool_name']
                    storage_info['san_ip'] = conf[section]['san_ip']
                    storage_info['san_login'] = conf[section]['san_login']
                    storage_info['san_password'] = conf[section]['san_password']
                elif 'lvm' in conf[section]['volume_driver']:
                    storage_info['volume_driver'] = 'lvm'
                    storage_info['volume_pod'] = volume_pod
                    storage_info['backend_host'] = conf[section]['backend_host']
                else:
                    logging.warning(
                        'Cannot distinguish corresponding volume driver type of %s' % volume_id)

                logging.info('Storage information about volume %s is %s' %
                             (volume_id, storage_info))
                return storage_info
    else:
        logging.warning(
            'Cannot find eligible volume backend for %s' % volume_id)
        return storage_info


def get_as5600_FJ_info(volume_id):
    '''
    Get volume information on as5600 storage such as FJ_Volume_Name for the volume.

    :param volume_id: uuid of volume.
    :return: volume information on as5600 storage
    '''

    var = 'echo ' + volume_id + ' >/tmp/volume_id;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
    sql_statement = '''"SELECT * FROM cinder.volumes WHERE id=\\'${volume_id}\\' and deleted=0\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    pipe = " | grep '   provider_location:'  | sed 's/provider_location: //'"
    res = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                           stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    res = [i.strip() for i in res if 'NULL' not in i]
    if res == []:
        logging.warning(
            'The volume %s might not belong as5600 type!' % volume_id)
        return 0
    else:
        as5600_FJ_info = json.loads(res[0].strip().strip('[').strip(']').replace(
            "'", "\"").replace("u\"", "\"").replace('None', 'null'))
        logging.info('The information of volume %s on as5600 storage is %s' % (
            volume_id, as5600_FJ_info))
        return as5600_FJ_info


def execute_g2_command(san_ip, san_login, san_password, cmd_list, volume_pod):
    '''
    Execute g2/g5 commands by ssh in specified volume pod.
    e.g.
    command = ['mcsinq', 'lshost', '-delim', '!']
    execute_g2_command('10.110.56.201', 'superuser', 'Passw0rd!', command, 'cinder-volume-1bd8f9848b-zzgbs')

    :param san_ip: ip of san.
    :param san_login: user of san.
    :param san_password: password of san.
    :param cmd_list: command list.
    :param volume_pod: run command in the volume pod.
    :return: response of ssh command.
    '''

    san_ip = '\'' + san_ip + '\''
    san_login = '\'' + san_login + '\''
    san_password = '\'' + san_password + '\''
    script_list = [None] * 8
    os.system(
        'ls /tmp/execute_g2_command.py 2>/dev/null && rm /tmp/execute_g2_command.py')
    os.system('touch /tmp/execute_g2_command.py')
    script_list[0] = 'import paramiko' + '\n'
    script_list[1] = 'ssh = paramiko.SSHClient()' + '\n'
    script_list[2] = 'ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())' + '\n'
    # e.g. ssh.connect('10.110.56.201', username='superuser', password='Passw0rd!')
    script_list[3] = 'ssh.connect(' + san_ip + ', ' + 'username=' + san_login + ', ' + \
                     'password=' + san_password + ')' + '\n'
    command = ' '.join(cmd_list)
    script_list[4] = 'stdin, stdout, stderr = ssh.exec_command(' + \
                     '\'' + command + '\'' + ')' + '\n'
    script_list[5] = 'resp = stdout.readlines()' + '\n'
    script_list[6] = 'print(resp)' + '\n'
    script_list[7] = 'stdin.close()' + '\n'
    with open('/tmp/execute_g2_command.py', 'a') as f:
        for script in script_list:
            f.write(script)
    cmd = "kubectl cp -n openstack /tmp/execute_g2_command.py " + \
          volume_pod + ":/tmp/execute_g2_command.py"
    subprocess.call(cmd, shell=True, executable='/bin/bash')
    os.system('rm /tmp/execute_g2_command.py')

    cmd1 = '''kubectl exec -it -n openstack ''' + volume_pod + ''' -- bash -c ''' + '''$\'''' + \
           '''python3 /tmp/execute_g2_command.py''' + '''\''''
    result = subprocess.Popen(cmd1, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                              encoding='utf8').stdout.readlines()
    # make result human-readable
    if len(result[0].split("\\n',")) > 1:
        # below result is analogous to stdout.readlines() in the codes
        temp_resp = result[0].split()
        resp = [None] * len(temp_resp)
        for i, j in enumerate(temp_resp):
            resp[i] = j.strip('[').strip(']').strip(
                ',').strip('\'').strip('\\n')
        logging.info('The result of command %s is %s' % (command, resp))
    # stderror rather than stdout output error
    elif result[0].strip() == '[]':
        logging.warning(
            'The result is empty or there is an error for g2 command %s!' % command)
        resp = []
    else:
        # resp there belongs to string type and it represents for one sentence.
        resp = result[0].strip('\n').strip(
            '[').strip(']').strip("'").strip('\\n')
        logging.info('The result of command %s is %s' % (command, resp))

    return resp


def as5600_command_is_status(value):
    """Check whether input value is status value or not."""
    try:
        if len(value) != 2:
            return False

        int(value, 16)
        int(value[0], 16)
        int(value[1], 16)

        return True
    except ValueError:
        return False


def execute_as5600_command(EternusIP, EternusUser, EternusPassword, exec_cmdline, volume_pod):
    '''
     Execute as5600 commands by ssh in specified volume pod.
     e.g.
    exec_cmdline = 'show host-wwn-names'
    execute_as5600_command('192.168.204.70', 'cinder', 'Cin549##', exec_cmdline, 'cinder-volume-3niua0mc6v-7zt2n')

    :param EternusIP: ip of san.
    :param EternusUser: user of san.
    :param EternusPassword: password of san.
    :param exec_cmdline: command line.
    :param volume_pod:  run command in the volume pod.
    :return: result, return code and output of ssh command.
    '''

    EternusIP = '\'' + EternusIP + '\''
    EternusUser = '\'' + EternusUser + '\''
    EternusPassword = '\'' + EternusPassword + '\''
    script_list = [None] * 22
    os.system(
        'ls /tmp/execute_as5600_command.py 2>/dev/null && rm /tmp/execute_as5600_command.py')
    os.system('touch /tmp/execute_as5600_command.py')
    script_list[0] = 'import paramiko'
    script_list[1] = 'import six'
    script_list[2] = 'ssh = paramiko.SSHClient()'
    script_list[3] = 'ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())'
    script_list[4] = 'ssh.connect(' + EternusIP + ', ' + 'username=' + EternusUser + ', ' + \
                     'password=' + EternusPassword + ')'
    script_list[5] = 'chan = ssh.invoke_shell()'
    script_list[6] = 'chan.send(' + '\'' + exec_cmdline + \
                     '\'' + ' + \'' + '\\n' + '\'' + ')'
    script_list[7] = 'stdoutdata = ' + '\'' + '\''
    script_list[8] = 'while True:'
    script_list[9] = '    temp = chan.recv(65535)'
    script_list[10] = '    if isinstance(temp, six.binary_type):'
    script_list[11] = '        temp = temp.decode(' + \
                      '\'' + 'utf-8' + '\'' + ')'
    script_list[12] = '    else:'
    script_list[13] = '        temp = str(temp)'
    script_list[14] = '    stdoutdata += temp'
    script_list[15] = '    if stdoutdata == ' + \
                      '\'' + '\\r\\nCLI> ' + '\'' + ':'
    script_list[16] = '        continue'
    script_list[17] = '    if (stdoutdata[len(stdoutdata) - 5: len(stdoutdata) - 1] =='
    script_list[18] = '        \'' + 'CLI>' + '\'' + '):'
    script_list[19] = '        break'
    script_list[20] = 'stdoutlist = stdoutdata.split(' + \
                      '\'' + '\\r\\n' + '\'' + ')'
    script_list[21] = 'print(stdoutlist)'
    with open('/tmp/execute_as5600_command.py', 'a') as f:
        for script in script_list:
            f.write(script + '\n')
    cmd = "kubectl cp -n openstack /tmp/execute_as5600_command.py " + \
          volume_pod + ":/tmp/execute_as5600_command.py"
    subprocess.call(cmd, shell=True, executable='/bin/bash')
    os.system('rm /tmp/execute_as5600_command.py')

    cmd1 = '''kubectl exec -it -n openstack ''' + volume_pod + ''' -- bash -c ''' + '''$\'''' + \
           '''python3 /tmp/execute_as5600_command.py''' + '''\''''
    result1 = subprocess.Popen(cmd1, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                               encoding='utf8').stdout.readlines()

    # below result is analogous to print(stdoutlist)
    # e.g.
    # ['', 'CLI> show host-wwn-names', '00', '005E', '0000\\tHOST_NAME#0\\t100000109BB15CE7\\t0000\\tDefault', '
    # ...'005D\\tHOST_NAME#93\\t100000109B107976\\t0000\\tDefault', 'CLI> ']
    stdoutlist = result1[0].strip().strip('[').strip(']').split(', ')
    stdoutlist = [i.strip("'") for i in stdoutlist]

    # analyze the stdoutlist
    output_header = ""
    for no, outline in enumerate(stdoutlist):
        if len(outline) <= 0 or outline is None:
            continue
        # such as 'CLI> show host-wwn-names'
        if not output_header.endswith(exec_cmdline):
            output_header += outline
            continue
        if 0 <= outline.find('Error'):
            logging.warning('An error happens in the command %s and output is %s' % (
                exec_cmdline, outline))
            return 0
        # such as '00'
        if not as5600_command_is_status(outline):
            continue
        status = int(outline, 16)
        lineno = no + 1
        break
    else:
        # some commands are not incorporated in as5600 driver but they might output empty value or
        # result which does not include status item. For example, that the result of the command
        # show volume-mapping is empty is indicative of no hostmap and that this command output result
        # which does not include status item might output hostmap relation.
        if len(stdoutlist) == 3 and stdoutlist[-1] == 'CLI> ':
            # output empty value
            message = []
            logging.info('The result of command %s is %s' %
                         (exec_cmdline, message))
            return {'result': 0, 'rc': '0', 'message': message}
        else:
            # there is no status item
            message = stdoutlist[2:]
            logging.info('The result of command %s is %s' %
                         (exec_cmdline, message))
            return {'result': 0, 'rc': '0', 'message': message}
    message = []
    output = []
    if status == 0:
        rc = '0'
        for outline in stdoutlist[lineno:]:
            if 0 <= outline.find('CLI>'):
                continue
            if len(outline) <= 0:
                continue
            if outline is None:
                continue
            message.append(outline)
        resp = {'result': 0, 'rc': rc, 'message': message}
        logging.info('The result of command %s is %s' % (exec_cmdline, resp))
        return resp
    else:
        code = stdoutlist[lineno]
        for outline in stdoutlist[lineno + 1:]:
            if 0 <= outline.find('CLI>'):
                continue
            if len(outline) <= 0:
                continue
            if outline is None:
                continue
            output.append(outline)
        SMIS_dic = {
            '0000': '0',  # Success.
            '0060': '32787',  # The device is in busy state.
            '0100': '4097'
        }  # Size not supported.
        if code in SMIS_dic:
            rc = SMIS_dic[code]
        else:
            # You can inspect errors in more details in the constants.py of as5600 volume drivers
            rc = 'E' + code
        message = output
        resp = {'result': 0, 'rc': rc, 'message': message}
        if 'rc' == '0':
            logging.info('The result of command %s is %s' %
                         (exec_cmdline, resp))
            return resp
        else:
            logging.warning('The result of command %s is %s' %
                            (exec_cmdline, resp))
            return 0


def get_volume_info_from_storage(volume_id):
    '''
    Retrieve useful information on storage such as target_lun.

    :param volume_id: uuid of volume.
    :return:  volume information from storage.
    '''

    storage_info = get_storage_info(volume_id)
    vol_info_from_storage = {}
    if 'as5600' in storage_info['volume_driver']:
        volume_pod = storage_info['volume_pod']
        volume_backend_name = storage_info['volume_backend_name']
        cinder_eternus_config_file = storage_info['cinder_eternus_config_file']
        EternusIP = storage_info['EternusIP']
        EternusPort = storage_info['EternusPort']
        EternusUser = storage_info['EternusUser']
        EternusPassword = storage_info['EternusPassword']
        EternusPool = storage_info['EternusPool']
        EternusSnapPool = storage_info['EternusSnapPool']
        as5600_FJ_info = get_as5600_FJ_info(volume_id)
        if as5600_FJ_info == 0:
            logging.warning(
                'Cannot retrieve provider_location of %s!' % (volume_id))
            return {}
        else:
            vol_name = as5600_FJ_info['vol_name']

            # retrieve host_lun, lun_group_name, e.g. 27, AFIN_GRP_#3
            exec_cmdline1 = 'show volume-mapping -volume-name ' + vol_name
            output1 = execute_as5600_command(
                EternusIP, EternusUser, EternusPassword, exec_cmdline1, volume_pod)
            if output1 == 0:
                logging.warning(
                    'An error happens in the command %s!' % exec_cmdline1)
                return {}
            elif output1['message'] == []:
                logging.warning(
                    'The hostmap of %s is None, please map it to a host first!' % volume_id)
                return {}
            else:
                target_lun_num = 0
                for i in output1['message']:
                    if vol_name in i:
                        vol_info_from_storage['multipath_id'] = '3' + \
                                                                i.split()[3].lower()
                        logging.info('multipath id of volume %s on storage is %s' % (
                            volume_id, vol_info_from_storage['multipath_id']))
                    if 'AFIN_GRP' in i:
                        # target lun belongs to int type
                        vol_info_from_storage['target_lun'] = int(
                            i.split()[0].strip())
                        vol_info_from_storage['lun_group_name'] = i.split()[
                            2].strip()
                        logging.info('target_lun and lun_group_name of volume %s on storage are respectively %s, %s' % (
                            volume_id, vol_info_from_storage['target_lun'], vol_info_from_storage['lun_group_name']))
                        target_lun_num += 1

                        # retrieve hostname such as HOST_NAME#8
                        exec_cmdline2 = 'show host-affinity -ag-name ' + \
                                        vol_info_from_storage['lun_group_name']
                        output2 = execute_as5600_command(EternusIP, EternusUser, EternusPassword, exec_cmdline2,
                                                         volume_pod)
                        if output2 == 0:
                            logging.warning(
                                'An error happens in the command %s' % exec_cmdline2)
                            return {}
                        else:
                            for i in output2['message']:
                                if vol_info_from_storage['lun_group_name'] in i:
                                    vol_info_from_storage['host_name_in_storage'] = i.split('\\t')[
                                        1]
                                    logging.info('host_name of volume %s on storage is %s' % (
                                        volume_id, vol_info_from_storage['host_name_in_storage']))
                                    break
                            else:
                                logging.warning(
                                    'Fail to get host name in command %s, and output is %s' % (exec_cmdline2, output2))
                                return {}

                        # retrieve port wwn such as 100000109BB15CE7
                        exec_cmdline3 = 'show host-wwn-names'
                        output3 = execute_as5600_command(EternusIP, EternusUser, EternusPassword, exec_cmdline3,
                                                         volume_pod)
                        if output3 == 0:
                            logging.warning(
                                'An error happens in the command %s' % exec_cmdline3)
                            return {}
                        else:
                            hostdatalist = {}
                            clidatalist = output3.get('message')
                            # clidatalist[1:] is the practical result
                            for clidataline in clidatalist[1:]:
                                clidata = clidataline.split('\\t')
                                hostdatalist[clidata[1]] = clidata[2]
                            for host_name, host_wwpn in hostdatalist.items():
                                if host_name == vol_info_from_storage['host_name_in_storage']:
                                    vol_info_from_storage['host_wwpn'] = host_wwpn.lower(
                                    )
                                    logging.info('host_wwpn of volume %s on storage is %s' % (
                                        volume_id, vol_info_from_storage['host_wwpn']))
                                    break
                            else:
                                logging.warning(
                                    'Fail to get host wwpn in command %s, and output is %s' % (exec_cmdline3, output3))
                                return {}

                        # determine analogous host name in openstack database
                        var = 'echo %' + \
                              vol_info_from_storage['host_wwpn'] + \
                              '% >/tmp/host_wwpn;'
                        var_transfer = '''host_wwpn=`cat /tmp/host_wwpn`;'''
                        sql_statement = '''"SELECT * FROM cinder.volume_attachment WHERE connector LIKE \\'${host_wwpn}\\'  LIMIT 1 OFFSET 0\G"'''
                        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
                              '''"''' + var + '''"''' + \
                              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
                              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
                              sql_statement + '''\''''
                        pipe = " | grep -i '  attached_host:'"
                        res = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                                               encoding='utf8').stdout.readlines()
                        if len(res) == 1 and 'NULL' not in res[0].strip():
                            host_name_in_database = res[0].strip().strip(
                                'attached_host:').strip()
                            hba_dict = get_hba_port(host_name_in_database)
                            if hba_dict == 0:
                                logging.warning(
                                    'Cannot acquire hba port on %s' % host_name_in_database)
                                return {}
                            else:
                                for port_name, port_state in hba_dict.copy().items():
                                    if 'online' not in port_state.lower():
                                        continue
                                    if port_name == vol_info_from_storage['host_wwpn']:
                                        logging.info(
                                            'The wwpn number on storage is consistent with that in cinder database for volume %s' % volume_id)
                                        vol_info_from_storage['host_name'] = host_name_in_database
                                        break
                                else:
                                    logging.warning(
                                        'Cannot acquire online hba port in cinder database which is same as that on storage for %s' % host_name_in_database)
                                    return {}
                        else:
                            logging.warning(
                                'Cannot find eligible host in cinder database in accordance with wwpn on storage!')
                            return {}

            if target_lun_num > 1:
                logging.warning(
                    'The hostmaps of volume %s are above one and this scenario cannot be processed!' % volume_id)
                return {}
    elif 'ceph' in storage_info['volume_driver']:
        volume_pod = storage_info['volume_pod']
        volume_backend_name = storage_info['volume_backend_name']
        rbd_ceph_conf = storage_info['rbd_ceph_conf']
        rbd_user = storage_info['rbd_user']
        rbd_pool = storage_info['rbd_pool']
        logging.warning(
            'No desired information for ceph volume from storage %s' % volume_id)
    elif 'g2/g5' in storage_info['volume_driver']:
        volume_pod = storage_info['volume_pod']
        volume_backend_name = storage_info['volume_backend_name']
        instorage_mcs_volpool_name = storage_info['instorage_mcs_volpool_name']
        san_ip = storage_info['san_ip']
        san_login = storage_info['san_login']
        san_password = storage_info['san_password']
        vol_name_id = get_volume_info(volume_id)['vol_name_id']
        if vol_name_id == 'None' or len(vol_name_id) == 0:
            ssh_cmd = ['mcsinq', 'lsvdiskhostmap',
                       '-delim', '!', '"volume-%s"' % volume_id]
        else:
            ssh_cmd = ['mcsinq', 'lsvdiskhostmap',
                       '-delim', '!', '"volume-%s"' % vol_name_id]
        resp = execute_g2_command(
            san_ip, san_login, san_password, ssh_cmd, volume_pod)
        if resp == []:
            logging.warning(
                'Cannot find %s in g2/g5 storage or the hostmap of %s is None!' % (volume_id, volume_id))
            return vol_info_from_storage
        elif isinstance(resp, list) and len(resp) == 2:
            key = resp[0].split('!')
            value = resp[1].split('!')
        elif isinstance(resp, list) and len(resp) > 2:
            logging.warning(
                'The hostmaps of volume %s are above one and this scenario cannot be processed!' % volume_id)
            return {}
        else:
            logging.warning('Encounter some abnormal problems!')
            return vol_info_from_storage
        hostmapdict = {}
        for i, j in zip(key, value):
            hostmapdict[i] = j
        vol_info_from_storage['multipath_id'] = '3' + \
                                                hostmapdict['vdisk_UID'].lower()
        # target lun belongs to int type
        vol_info_from_storage['target_lun'] = int(hostmapdict['SCSI_id'])
        # host_name here for g2 is host_name_in_storage
        vol_info_from_storage['host_name'] = hostmapdict['host_name']
    elif 'lvm' in storage_info['volume_driver']:
        volume_pod = storage_info['volume_pod']
        backend_host = storage_info['backend_host']
        logging.warning(
            'No desired information for lvm volume from storage %s' % volume_id)
    else:
        logging.warning(
            'Cannot distinguish corresponding volume driver type of %s' % volume_id)

    logging.info('The desired information about volume %s from storage is %s' % (
        volume_id, vol_info_from_storage))
    return vol_info_from_storage


def get_hba_port(hostname):
    '''
    Retrieve hba information for specified host_name.

    :param hostname: specified host name.
    :return: hba information dict or 0 is indicative of failing to get hba port.
    '''

    # get nova compute pod
    cmd = "kubectl get pod -n openstack -owide | grep -i nova-compute | grep -i " + hostname \
          + " | awk '{print $1}'"
    res = os.popen(cmd).readlines()
    if len(res) == 1:
        compute_pod = res[0].strip()
    else:
        logging.warning('Find not one compute pod by hostname %s' % hostname)
        return 0

    # get wwpns by systool in nova-compute-pod
    cmd1 = '''kubectl exec -it -n openstack ''' + compute_pod + ''' -- bash -c ''' + \
           '''$\'''' + '''systool -c fc_host -v | egrep -i \\'port_name|port_state\\' ''' + '''\''''
    res1 = subprocess.Popen(cmd1, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                            encoding='utf8').stdout.readlines()
    if 'Error opening class fc_host' in res1[0]:
        logging.warning('The host %s does not have hba card!' % hostname)
    elif len(res1) > 1:
        hba_dict = {}
        for idx, value in enumerate(res1):
            if idx % 2 == 0:
                port_name = value.strip().strip('port_name').strip(
                    'port_state').strip().strip('=').strip().strip('"')
                if '0x' in port_name:
                    port_name = port_name[2:]
                port_state = res1[idx + 1].strip().strip('port_name').strip(
                    'port_state').strip().strip('=').strip().strip('"')
                hba_dict[port_name] = port_state
        logging.info('The hba port information of %s is %s' %
                     (hostname, hba_dict))
        return hba_dict
    else:
        logging.warning(
            'Encounter some abnormal problems and result is %s!' % res1)

    return 0


def validate_three_pod_consistency(volume_id):
    '''
    Determine whether the data in three mariadb pod are consistent by inspecting
    connection info of a volume in them.

    :param volume_id: uuid of volume
    :return: True is indicative of consistency.
    '''

    var = 'echo ' + volume_id + ' >/tmp/volume_id;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
    sql_statement = '''"SELECT * FROM nova.block_device_mapping WHERE volume_id=\\'${volume_id}\\' and deleted=0\G"'''
    cmd0 = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
           '''"''' + var + '''"''' + \
           ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
           '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
           sql_statement + '''\''''
    pipe0 = " | grep -i connection_info | sed 's/connection_info: //'"
    res0 = subprocess.Popen(cmd0 + pipe0, shell=True, executable='/bin/bash',
                            stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()

    if len(res0) == 0:
        logging.warning(
            'Please choose a volume which is valid and whose state is in-use!')
    else:
        cmd1 = '''kubectl exec -it -n openstack mariadb-server-1 -c mariadb -- bash -c ''' + \
               '''"''' + var + '''"''' + \
               ''';kubectl exec -it -n openstack mariadb-server-1 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
               '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
               sql_statement + '''\''''
        pipe1 = " | grep -i connection_info | sed 's/connection_info: //'"
        res1 = subprocess.Popen(cmd1 + pipe1, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                                encoding='utf8').stdout.readlines()
        cmd2 = '''kubectl exec -it -n openstack mariadb-server-2 -c mariadb -- bash -c ''' + \
               '''"''' + var + '''"''' + \
               ''';kubectl exec -it -n openstack mariadb-server-2 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
               '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
               sql_statement + '''\''''
        pipe2 = " | grep -i connection_info | sed 's/connection_info: //'"
        res2 = subprocess.Popen(cmd2 + pipe2, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                                encoding='utf8').stdout.readlines()
        if res0 == res1 and res1 == res2:
            logging.info('The data in three mariadb pod are consistent!')
            return True
        else:
            logging.error('The data in three mariadb pod are not consistent!')
            return False


def validate_forced_host(forced_host):
    '''
    Guarantee the format of forced_host is invalid.

    :param force_host: explicit host name.
    :return: True indicates host is valid.
    '''

    # the name of host should include 'compute' instead of residing in it.
    if forced_host in 'compute':
        return False

    info = {}
    cmd = "openstack hypervisor list | grep " + \
          forced_host + " | awk '{print $4}'"
    res = execute_openstack_cmd(cmd)
    if len(res) > 0:
        hypervisor_hostname = res[0].strip()
        logging.info('The hypervisor_hostname of forced_host %s is %s' %
                     (forced_host, hypervisor_hostname))
        return True
    else:
        logging.info('The format of forced_host %s is invalid!' % forced_host)
        return False


def ensure_attachment_num_and_relation(volume_id):
    '''
    Guarantee there is only one attachment for a volume
    which does not support multiattach in cinder and make
    sure attachment_id in nova is not null.

    :param volume_id: uuid of volume.
    :return: attachment_id of connection info or zero
             which is indicative of failing to revise connection info.
    '''

    multiattach = get_volume_info(volume_id)['multiattach']
    if multiattach != 'False':
        logging.warning(
            'Revising operation cannot be performed since the volume %s supports multiattach!' % volume_id)
        return 0

    # get attachment_id
    var = 'echo ' + volume_id + ' >/tmp/volume_id;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
    sql_statement = '''"SELECT * FROM nova.block_device_mapping WHERE volume_id=\\'${volume_id}\\' and deleted=0\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    pipe = " | grep -i attachment_id | sed 's/attachment_id: //'"
    res = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                           stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    if len(res) == 1 and 'NULL' not in res[0].strip():
        attachment_id = res[0].strip()

        # investigate whether above one attachment for a volume which does not support multiattach in cinder is present
        if multiattach == 'False':
            var = 'echo ' + volume_id + ' >/tmp/volume_id;'
            var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
            sql_statement = '''"SELECT * FROM cinder.volume_attachment WHERE volume_id=\\'${volume_id}\\' and deleted=0\G"'''
            cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
                  '''"''' + var + '''"''' + \
                  ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
                  '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
                  sql_statement + '''\''''
            pipe = " | grep -i '   id:'"
            res = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                                   encoding='utf8').stdout.readlines()
            # e.g. "  id: 3b0757d6-dd6a-4b97-b4d5-b83ca99faa02" and i.strip()[4:] is 3b0757d6-dd6a-4b97-b4d5-b83ca99faa02
            res = [i.strip()[4:] for i in res if 'id' in i]
            if len(res) > 1:
                logging.warning(
                    'The attachment of volume %s in cinder is above one, they are %s' % (volume_id, res))
                var = 'echo ' + attachment_id + ' >/tmp/attachment_id;' + \
                      'echo ' + volume_id + ' >/tmp/volume_id;'
                var_transfer = '''attachment_id=`cat /tmp/attachment_id`;''' + \
                               '''volume_id=`cat /tmp/volume_id`;'''
                sql_statement = '''"UPDATE cinder.volume_attachment SET deleted=1 WHERE volume_id=\\'${volume_id}\\' and id!=\\'${attachment_id}\\'\G"'''
                cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
                      '''"''' + var + '''"''' + \
                      ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
                      '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
                      sql_statement + '''\''''
                subprocess.call(cmd, shell=True, executable='/bin/bash')
            # ensure cinder attachment with same attachment id is valid
            var = 'echo ' + attachment_id + ' >/tmp/attachment_id;' + \
                  'echo ' + volume_id + ' >/tmp/volume_id;'
            var_transfer = '''attachment_id=`cat /tmp/attachment_id`;''' + \
                           '''volume_id=`cat /tmp/volume_id`;'''
            sql_statement = '''"UPDATE cinder.volume_attachment SET deleted=0 WHERE volume_id=\\'${volume_id}\\' and id=\\'${attachment_id}\\'\G"'''
            cmd2 = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
                   '''"''' + var + '''"''' + \
                   ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
                   '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
                   sql_statement + '''\''''
            subprocess.call(cmd2, shell=True, executable='/bin/bash')
    elif len(res) == 1 and 'NULL' in res[0].strip():
        logging.warning(
            'The attachment id of volume %s in nova is NULL!' % volume_id)
        # set a valid value for attachment_id
        var = 'echo ' + volume_id + ' >/tmp/volume_id;'
        var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
        sql_statement = '''"SELECT * FROM cinder.volume_attachment WHERE volume_id=\\'${volume_id}\\' LIMIT 1 OFFSET 0\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        pipe = " | grep -i '   id:'"
        res = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                               encoding='utf8').stdout.readlines()
        # e.g. "  id: 3b0757d6-dd6a-4b97-b4d5-b83ca99faa02" and i.strip()[4:] is 3b0757d6-dd6a-4b97-b4d5-b83ca99faa02
        res = [i.strip()[4:] for i in res if 'id' in i]
        if len(res) == 1:
            attachment_id = res[0]
            var = 'echo ' + attachment_id + ' >/tmp/attachment_id;' + \
                  'echo ' + volume_id + ' >/tmp/volume_id;'
            var_transfer = '''attachment_id=`cat /tmp/attachment_id`;''' + \
                           '''volume_id=`cat /tmp/volume_id`;'''
            sql_statement = '''"UPDATE nova.block_device_mapping SET attachment_id=\\'${attachment_id}\\' WHERE volume_id=\\'${volume_id}\\' and deleted=0\G"'''
            cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
                  '''"''' + var + '''"''' + \
                  ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
                  '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
                  sql_statement + '''\''''
            subprocess.call(cmd, shell=True, executable='/bin/bash')
            # Making sure deleted is 0 in the record where new attachment_id is adopted.
            var = 'echo ' + attachment_id + ' >/tmp/attachment_id;'
            var_transfer = '''attachment_id=`cat /tmp/attachment_id`;'''
            sql_statement = '''"UPDATE cinder.volume_attachment SET deleted=0 WHERE id=\\'${attachment_id}\\'\G"'''
            cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
                  '''"''' + var + '''"''' + \
                  ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
                  '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
                  sql_statement + '''\''''
            subprocess.call(cmd, shell=True, executable='/bin/bash')
            logging.info(
                'Set a valid value for attachment_id in nova for volume %s' % volume_id)
        else:
            logging.warning(
                'Fail to set a valid value for attachment id in nova for volume %s !' % volume_id)
            attachment_id = None
            return 0
    else:
        logging.warning(
            'All attachments in nova of volume %s are deleted or the volume id is invalid' % volume_id)
        attachment_id = None
        return 0

    return {'attachment_id': attachment_id}


def has_retype_operation(volume_id):
    '''
    Determine whether retype operation has started.

    :param volume_id: uuid of volume
    :return: True is indicative of having retype operation
    '''

    has_new_volume = False

    # get new volume info
    migration_status = 'target:' + volume_id
    var = 'echo ' + migration_status + ' >/tmp/migration_status;'
    var_transfer = '''migration_status=`cat /tmp/migration_status`;'''
    sql_statement = '''"SELECT * FROM cinder.volumes WHERE migration_status=\\'${migration_status}\\'\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    pipe = " | egrep '  id:|  host:|  volume_type_id:|  service_uuid:' | sed 's/.*: //g'"
    res1 = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                            stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    if len(res1) > 0:
        new_volume_id = res1[0].strip()
        new_volume_host = res1[1].strip()
        new_volume_volume_type_id = res1[2].strip()
        new_volume_service_uuid = res1[3].strip()
        logging.info(
            'The information of new volume is %s' % {'new_volume_id': new_volume_id, 'new_volume_host': new_volume_host,
                                                     'new_volume_volume_type_id': new_volume_volume_type_id,
                                                     'new_volume_service_uuid': new_volume_service_uuid})
        has_new_volume = True
        subprocess.call('echo "The new volume information is:"',
                        shell=True, executable='/bin/bash')
        subprocess.call(cmd, shell=True, executable='/bin/bash')
    else:
        logging.warning(
            'There are not new volume during retype operation of volume %s' % volume_id)
        return 0

    # get original volume info
    var = 'echo ' + volume_id + ' >/tmp/volume_id;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
    sql_statement = '''"SELECT * FROM cinder.volumes WHERE id=\\'${volume_id}\\'\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    pipe = " | egrep '  host:|  volume_type_id:|  migration_status:|  service_uuid:' | sed 's/.*: //g'"
    res1 = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                            stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    if len(res1) > 0:
        org_volume_host = res1[0].strip()
        org_volume_volume_type_id = res1[1].strip()
        org_volume_migration_status = res1[2].strip()
        org_volume_service_uuid = res1[3].strip()
        logging.info(
            'The information of original volume is %s' % {'volume_id': volume_id, 'org_volume_host': org_volume_host,
                                                          'org_volume_volume_type_id': org_volume_volume_type_id,
                                                          'org_volume_service_uuid': org_volume_service_uuid})
        if has_new_volume:
            subprocess.call('echo "The original volume information is:"',
                            shell=True, executable='/bin/bash')
            subprocess.call(cmd, shell=True, executable='/bin/bash')
    else:
        logging.warning('Can not find volume %s information!' % volume_id)
        return 0

    return has_new_volume


def find_connection_template(instance_id, volume_id, forced_host=None):
    '''
    Find template of connection info and connector in cinder
    or nova.
    :param instance_id: uuid of instance.
    :param volume_id: uuid of volume.
    :param forced_host: uuid of volume.
    :return: connection info of nova and cinder in dict type or zero
             which is indicative of failing to get connection info.
    '''

    # collect volumes which belongs to the same host of the instance
    instance_info = get_instance_info(instance_id)
    if forced_host == None:
        hostname = instance_info['hostname']
    else:
        hostname = forced_host
    var = 'echo ' + hostname + ' >/tmp/hostname;'
    var_transfer = '''hostname=`cat /tmp/hostname`;'''
    sql_statement = '''"SELECT * FROM cinder.volume_attachment WHERE attached_host=\\'${hostname}\\' and deleted=0 and connection_info is not NULL\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    pipe = " | grep 'volume_id:' | awk 'FS=\":\" {print $2}'"
    res1 = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                            stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    vol_list1 = [i.strip() for i in res1]

    # collect volumes which belongs to the same host of the volume
    volume_info = get_volume_info(volume_id)
    vol_host = volume_info['vol_host']
    if vol_host is None:
        logging.warning(
            'Fail to find connection template since the host of volume %s is None' % volume_id)
        return 0
    var = 'echo ' + vol_host + ' >/tmp/vol_host;'
    var_transfer = '''vol_host=`cat /tmp/vol_host`;'''
    sql_statement = '''"SELECT * FROM cinder.volumes WHERE host=\\'${vol_host}\\' and deleted=0\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    pipe = " | grep '   id:' | awk 'FS=\":\" {print $2}'"
    res2 = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                            stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    vol_list2 = [i.strip() for i in res2]

    # get a volume which complies with certain compute host and vol_host
    vol_list = list(set(vol_list1) & set(vol_list2))
    if len(vol_list) == 0:
        logging.warning('Fail to find connection template since there is not an attached volume of %s host in %s!'
                        % (volume_info['vol_host'], hostname))
        return 0

    for vol_sel in vol_list:
        if vol_sel == volume_id:
            continue
        # get connection_info from nova database
        var = 'echo ' + vol_sel + ' >/tmp/vol_sel;'
        var_transfer = '''vol_sel=`cat /tmp/vol_sel`;'''
        sql_statement = '''"SELECT * FROM nova.block_device_mapping WHERE volume_id=\\'${vol_sel}\\' and deleted=0 and connection_info is not NULL\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        pipe = " | grep connection_info | sed 's/connection_info: //'"
        res3 = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                                stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
        if len(res3) > 0:
            nova_conn_info = json.loads(res3[0].strip())
        else:
            logging.warning('Fail to get connection_info from nova database!')
            continue

        # get connection_info and connector from cinder database
        var = 'echo ' + vol_sel + ' >/tmp/vol_sel;'
        var_transfer = '''vol_sel=`cat /tmp/vol_sel`;'''
        sql_statement = '''"SELECT * FROM cinder.volume_attachment WHERE volume_id=\\'${vol_sel}\\' and deleted=0 and connection_info is not NULL\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        pipe = " | grep connect | sed 's/connection_info: //' | sed 's/connector: //'"
        res4 = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                                stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
        if len(res4) > 0:
            cinder_conn_info = json.loads(res4[0].strip())
            cinder_connector = json.loads(res4[1].strip())
            break
        else:
            logging.warning(
                'Fail to get connection_info from cinder database!')
    else:
        logging.warning(
            'Fail to get connection_info from nova and cinder database!')
        return 0
    conn_info_template = {'nova_conn_info': nova_conn_info,
                          'cinder_conn_info': cinder_conn_info, 'cinder_connector': cinder_connector}
    logging.info(
        'The conn_info template from cinder and nova database is %s.' % conn_info_template)

    return conn_info_template


def revise_none_type(volume_id):
    '''
    Convert the none type to eligible type according to vol_host

    :param volume_id: uuid of volume
    :return: uuid of volume
    '''

    # determine whether the type of volume is None
    vol_info = get_volume_info(volume_id)
    if vol_info['type'] != 'None':
        logging.warning(
            'The volume type of the volume %s is not None!' % volume_id)
        return 0

    # get volume_backend_name according to vol_host
    vol_host = vol_info['vol_host']
    cmd1 = "cinder get-pools --detail | egrep ' name|volume_backend'" + " | grep -A 1 " + vol_host + \
           " | grep -i volume_backend_name | awk '{print $4}'"
    res1 = execute_openstack_cmd(cmd1)
    volume_backend_name = res1[0].strip()

    # get type according to volume_backend_name
    cmd2 = "openstack volume type list --long | grep $'volume_backend_name=\\'" + volume_backend_name + "\\''" + \
           " | cut -d ' ' -f 2,4 | grep -v 'volume_for_glance'"
    res2 = execute_openstack_cmd(cmd2)
    if len(res2) > 0:
        volume_type_id = res2[0].split()[0]
        volume_type_name = res2[0].split()[1]
        logging.info('The volume type for the volume %s is replaced to %s!' % (
            volume_id, volume_type_name))

        # revise none type
        var = 'echo ' + volume_id + ' >/tmp/volume_id;' + \
              'echo ' + volume_type_id + ' >/tmp/volume_type_id;'
        var_transfer = '''volume_id=`cat /tmp/volume_id`;''' + \
                       '''volume_type_id=`cat /tmp/volume_type_id`;'''
        sql_statement = '''"UPDATE cinder.volumes SET volume_type_id=\\'${volume_type_id}\\' ''' + \
                        '''WHERE id=\\'${volume_id}\\'\G"'''
        cmd3 = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
               '''"''' + var + '''"''' + \
               ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
               '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
               sql_statement + '''\''''
        subprocess.call(cmd3, shell=True, executable='/bin/bash')
    else:
        logging.warning(
            'Cannot find the eligible type for volume %s' % volume_id)
        return 0

    return volume_id


def map_volume_to_host(volume_id, host_name):
    '''
    In the case of g2 or as5600 type, map volume to specified host.

    :param volume_id: uuid of volume
    :param host_name:  specified host name.
    :return:
    '''

    hba_dict = get_hba_port(host_name)
    if hba_dict == 0:
        logging.warning(
            'Fail to map the volume %s to %s since hba information has not been found!' % (volume_id, host_name))
        return 0

    storage_info = get_storage_info(volume_id)
    if 'as5600' in storage_info['volume_driver']:
        volume_pod = storage_info['volume_pod']
        volume_backend_name = storage_info['volume_backend_name']
        cinder_eternus_config_file = storage_info['cinder_eternus_config_file']
        EternusIP = storage_info['EternusIP']
        EternusPort = storage_info['EternusPort']
        EternusUser = storage_info['EternusUser']
        EternusPassword = storage_info['EternusPassword']
        EternusPool = storage_info['EternusPool']
        EternusSnapPool = storage_info['EternusSnapPool']
        as5600_FJ_info = get_as5600_FJ_info(volume_id)
        if as5600_FJ_info == 0:
            logging.warning(
                'Cannot retrieve provider_location of %s!' % (volume_id))
            return 0
        else:
            vol_name = as5600_FJ_info['vol_name']

            # determine whether the volume has hostmap
            exec_cmdline1 = 'show volume-mapping -volume-name ' + vol_name
            output1 = execute_as5600_command(
                EternusIP, EternusUser, EternusPassword, exec_cmdline1, volume_pod)
            if output1 == 0:
                logging.warning(
                    'An error happens in the command %s!' % exec_cmdline1)
                return 0
            elif output1['message'] == []:
                # find host name on storage in accordance with wwpn such as HOST_NAME#8
                exec_cmdline2 = 'show host-wwn-names'
                output2 = execute_as5600_command(
                    EternusIP, EternusUser, EternusPassword, exec_cmdline2, volume_pod)
                if output2 == 0:
                    logging.warning(
                        'An error happens in the command %s!' % exec_cmdline2)
                    return 0
                else:
                    hostdatalist = {}
                    clidatalist = output2.get('message')
                    # clidatalist[1:] is the practical result
                    for clidataline in clidatalist[1:]:
                        clidata = clidataline.split('\\t')
                        hostdatalist[clidata[1]] = clidata[2]
                    # remove port which is not online
                    for port_name, port_state in hba_dict.copy().items():
                        if port_state.lower() != 'online':
                            hba_dict.pop(port_name)
                    for hostname, hostwwpn in hostdatalist.items():
                        if hostwwpn.lower() in hba_dict:
                            host_name_on_storage = hostname
                            logging.info('The host name on storage for host %s is %s' % (
                                host_name, host_name_on_storage))
                            break
                    else:
                        logging.warning(
                            'Fail to get host name accroding hba port %s on storage in command %s' % (
                            hba_dict, exec_cmdline2))
                        return 0

                # determine eligible lun_group such as AFIN_GRP_#3
                exec_cmdline3 = 'show host-affinity -host-name ' + host_name_on_storage
                output3 = execute_as5600_command(
                    EternusIP, EternusUser, EternusPassword, exec_cmdline3, volume_pod)
                if output3 == 0:
                    logging.warning(
                        'An error happens in the command %s!' % exec_cmdline3)
                    return 0
                else:
                    for i in output3['message']:
                        if host_name_on_storage in i:
                            lun_group_name = i.split('\\t')[3]
                            logging.info('The lun_group_name on storage for host %s is %s' % (
                                host_name, lun_group_name))
                            break
                    else:
                        logging.warning(
                            'Fail to get lun_group_name in command %s, and output is %s' % (exec_cmdline3, output3))
                        return 0

                # find unused lun number
                exec_cmdline4 = 'show affinity-group -ag-name ' + lun_group_name
                output4 = execute_as5600_command(
                    EternusIP, EternusUser, EternusPassword, exec_cmdline4, volume_pod)
                if output4 == 0:
                    logging.warning(
                        'An error happens in the command %s!' % exec_cmdline4)
                    return 0
                else:
                    datalist = []
                    used_nos = []
                    clidatalist = output4.get('message')
                    for clidataline in clidatalist[3:]:
                        clidata = clidataline.split('\\t')
                        no = int(clidata[0], 16)
                        used_nos.append(no)
                    for i in range(256):
                        if i not in used_nos:
                            unused_num = i
                            logging.info('Acquired unused lun number %s for volume_id:%s' % (
                                unused_num, volume_id))
                            break
                    else:
                        logging.warning(
                            'The volumes in affinity group %s is full(256)!' % lun_group_name)
                        return 0

                # add volume to specifc lun_group
                # e.g. set affinity-group -ag-name AFIN_GRP_#2 -volume-name FJosv_4xjeuhJJqxyaf-MaInvPng== -lun 0
                # In addition, delete command is 'delete affinity-group -ag-name AFIN_GRP_#2 -lun 255'
                exec_cmdline5 = 'set affinity-group ' + '-ag-name ' + lun_group_name + \
                                ' -volume-name ' + vol_name + ' -lun ' + str(unused_num)
                output5 = execute_as5600_command(
                    EternusIP, EternusUser, EternusPassword, exec_cmdline5, volume_pod)
                if 'message' in output5 and output5['message'] == []:
                    logging.info('Succeed in mapping volume %s(%s) to host %s, and mapping information is: '
                                 '{host_name_on_storage:%s, lun_group_name:%s, target_lun:%s}' % (
                                 vol_name, volume_id, host_name, host_name_on_storage, lun_group_name, unused_num))
                    return '{vol_name:%s(%s), host_name_on_storage:%s, lun_group_name:%s, target_lun:%s}' % (
                    vol_name, volume_id, host_name_on_storage, lun_group_name, unused_num)
                else:
                    logging.warning(
                        'An error happens in the command %s!' % exec_cmdline5)
                    return 0
            else:
                for i in output1['message']:
                    if vol_name in i:
                        multipath_id = '3' + i.split()[3].lower()
                    if 'AFIN_GRP' in i:
                        target_lun = int(i.split()[0].strip())
                        lun_group_name = i.split()[2].strip()
                        break
                else:
                    lun_group_name = None
                    logging.warning(
                        'Cannot find affinity group which includes volume %s' % vol_name)
                logging.warning('The volume %s has already mapped to a host and lun_group_name is %s' % (
                    volume_id, lun_group_name))
                return 0
    elif 'ceph' in storage_info['volume_driver']:
        logging.info(
            'The ceph volume %s does not need to map to a host!' % volume_id)
    elif 'g2/g5' in storage_info['volume_driver']:
        volume_pod = storage_info['volume_pod']
        volume_backend_name = storage_info['volume_backend_name']
        instorage_mcs_volpool_name = storage_info['instorage_mcs_volpool_name']
        san_ip = storage_info['san_ip']
        san_login = storage_info['san_login']
        san_password = storage_info['san_password']

        # find host name in accordance with wwpn
        for port_name, port_state in hba_dict.copy().items():
            if 'online' not in port_state.lower():
                continue
            ssh_cmd = ['mcsinq', 'lsfabric', '-delim', '!', '-wwpn', port_name]
            resp = execute_g2_command(
                san_ip, san_login, san_password, ssh_cmd, volume_pod)
            if resp == []:
                continue
            elif isinstance(resp, list) and len(resp) > 1:
                resp_list = []
                for i in resp:
                    resp_list.append(i.split('!'))
                resp_new = list(zip(*resp_list))
                fabricdict = {}
                for j in resp_new:
                    fabricdict[j[0]] = j[1:]
                host_name_from_fabric = fabricdict['name'][0]
                break
            else:
                logging.warning(
                    'Encounter some abnormal problems while command %s is executed!' % ssh_cmd)
                return 0
        else:
            logging.warning('Fail to map the volume %s to %s since there is not a eligible host in storage' % (
                volume_id, host_name))
            return 0
        # inspect whether the volume has mapped to one host
        vol_name_id = get_volume_info(volume_id)['vol_name_id']
        if vol_name_id == 'None':
            ssh_cmd2 = ['mcsinq', 'lsvdiskhostmap',
                        '-delim', '!', '"volume-%s"' % volume_id]
        else:
            ssh_cmd2 = ['mcsinq', 'lsvdiskhostmap',
                        '-delim', '!', '"volume-%s"' % vol_name_id]
        resp2 = execute_g2_command(
            san_ip, san_login, san_password, ssh_cmd2, volume_pod)
        if resp2 == []:
            # map the volume to selected host
            if vol_name_id == 'None':
                ssh_cmd3 = ['mcsop', 'mkvdiskhostmap', '-host', '"%s"' %
                            host_name_from_fabric, '"volume-%s"' % volume_id]
            else:
                ssh_cmd3 = ['mcsop', 'mkvdiskhostmap', '-host', '"%s"' %
                            host_name_from_fabric, '"volume-%s"' % vol_name_id]
            resp3 = execute_g2_command(
                san_ip, san_login, san_password, ssh_cmd3, volume_pod)
            if isinstance(resp3, str):
                logging.info('Succeed in mapping volume %s to host %s, and mapping information is %s' % (
                    volume_id, host_name, resp3))
                return resp3
            else:
                logging.warning(
                    'Encounter some abnormal problems while command %s is executed!' % ssh_cmd3)
        elif isinstance(resp2, list) and len(resp2) > 1:
            key = resp2[0].split('!')
            value = resp2[1].split('!')
            hostmapdict = {}
            for i, j in zip(key, value):
                hostmapdict[i] = j
            logging.warning('The volume %s has mapped to host %s!' %
                            (volume_id, hostmapdict['host_name']))
        else:
            logging.warning(
                'Encounter some abnormal problems while command %s is executed!' % ssh_cmd2)
    elif 'lvm' in storage_info['volume_driver']:
        logging.info(
            'The lvm volume %s does not need to map to a host!' % volume_id)
    else:
        logging.warning(
            'Cannot distinguish corresponding volume driver type of %s' % volume_id)

    return 0


def unmap_volume_from_host(volume_id, host_name):
    '''
    In the case of g2 or as5600 type, unmap volume from a specified host.

    :param volume_id: uuid of volume.
    :param host_name:
    :return: 0 is indicative of failing to unmap volume from a specified host.
    '''

    volume_info = get_volume_info(volume_id)
    multiattach = volume_info['multiattach']
    if multiattach != 'False':
        logging.warning(
            'Unmapping operation cannot be performed since the volume %s supports multiattach!' % volume_id)
        return 0

    # ensure no instance is using the volume which will be unmapped
    vol_info_from_storage = get_volume_info_from_storage(volume_id)
    if vol_info_from_storage == {}:
        logging.warning(
            'Cannot acquire volume information from storage for volume %s' % volume_id)
        return 0
    if host_name not in vol_info_from_storage['host_name']:
        logging.warning('The specified host %s does not comply with host name %s in the storage!' %
                        (host_name, vol_info_from_storage['host_name']))
        return 0
    multipath_id = vol_info_from_storage['multipath_id']
    # get libvirt pod
    cmd1 = "kubectl get pod -n openstack -owide | grep -i libvirt | grep -i " + host_name \
           + " | awk '{print $1}'"
    libvirt_pod = os.popen(cmd1).readlines()[0].strip()
    # enter libvirt pod and retrieve block information
    virsh_cmd = '''for i in `virsh list | grep [0-9] | awk \\'{print $1}\\'`;do virsh domblklist $i | grep vd;done'''
    cmd2 = '''kubectl exec -it -n openstack ''' + libvirt_pod + \
           ''' -- bash -c ''' + '''$\'''' + virsh_cmd + '''\''''
    res = subprocess.Popen(cmd2, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                           encoding='utf8').stdout.readlines()
    for path in res:
        if multipath_id in path:
            logging.warning('The volume %s is used by an instance' % volume_id)
            return 0
        if 'by-path' in path or '/dev/sd' in path:
            logging.warning(
                'There are some single paths instead of multipath in %s!' % libvirt_pod)
            return 0
    else:
        logging.info(
            'The volume %s is not used by an instance and all paths are multipath!' % volume_id)

    # unmap volume from host
    storage_info = get_storage_info(volume_id)
    if 'as5600' in storage_info['volume_driver']:
        volume_pod = storage_info['volume_pod']
        volume_backend_name = storage_info['volume_backend_name']
        cinder_eternus_config_file = storage_info['cinder_eternus_config_file']
        EternusIP = storage_info['EternusIP']
        EternusPort = storage_info['EternusPort']
        EternusUser = storage_info['EternusUser']
        EternusPassword = storage_info['EternusPassword']
        EternusPool = storage_info['EternusPool']
        EternusSnapPool = storage_info['EternusSnapPool']
        as5600_FJ_info = get_as5600_FJ_info(volume_id)
        if as5600_FJ_info == 0:
            logging.warning(
                'Cannot retrieve provider_location of %s!' % (volume_id))
            return 0
        else:
            vol_name = as5600_FJ_info['vol_name']
            # e.g. set affinity-group -ag-name AFIN_GRP_#2 -volume-name FJosv_4xjeuhJJqxyaf-MaInvPng== -lun 0
            # In addition, delete command is 'delete affinity-group -ag-name AFIN_GRP_#2 -lun 255'
            # There is one caveat, if affinity-group only has one lun, the lun cannot be removed unless the affinity
            # group are deleted before all connectivities are deleted for relative host.
            exec_cmdline = 'delete affinity-group ' + '-ag-name ' + \
                           vol_info_from_storage['lun_group_name'] + \
                           ' -lun ' + str(vol_info_from_storage['target_lun'])
            output = execute_as5600_command(
                EternusIP, EternusUser, EternusPassword, exec_cmdline, volume_pod)
            if output == 0:
                logging.warning(
                    'An error happens in the command %s!' % exec_cmdline)
                return 0
            elif output['message'] == []:
                logging.info('Succeed in unmapping volume %s from host %s' % (
                    volume_id, host_name))
                return 1
    elif 'ceph' in storage_info['volume_driver']:
        logging.info(
            'The ceph volume %s does not need to unmap from a host!' % volume_id)
    elif 'g2/g5' in storage_info['volume_driver']:
        volume_pod = storage_info['volume_pod']
        volume_backend_name = storage_info['volume_backend_name']
        instorage_mcs_volpool_name = storage_info['instorage_mcs_volpool_name']
        san_ip = storage_info['san_ip']
        san_login = storage_info['san_login']
        san_password = storage_info['san_password']
        vol_name_id = get_volume_info(volume_id)['vol_name_id']
        if vol_name_id == 'None':
            # e.g. mcsop rmvdiskhostmap -host "compute-007-20281250" "volume-fe56fae3-c5ef-4fea-b08f-731e474f025"
            ssh_cmd = ['mcsop', 'rmvdiskhostmap', '-host', '"%s"' %
                       vol_info_from_storage['host_name'], '"volume-%s"' % volume_id]
        else:
            ssh_cmd = ['mcsop', 'rmvdiskhostmap', '-host', '"%s"' %
                       vol_info_from_storage['host_name'], '"volume-%s"' % vol_name_id]
        resp = execute_g2_command(
            san_ip, san_login, san_password, ssh_cmd, volume_pod)
        if resp == []:
            logging.info('The result of rmvdiskhostmap is empty and succeed in unmapping volume %s from host %s' % (
                volume_id, host_name))
            return 1
        else:
            logging.warning(
                'Encounter some abnormal problems while command %s is executed!' % ssh_cmd)
    elif 'lvm' in storage_info['volume_driver']:
        logging.info(
            'The lvm volume %s does not need unmap to a host!' % volume_id)
    else:
        logging.warning(
            'Cannot distinguish corresponding volume driver type of %s' % volume_id)

    return 0


def revise_connection_info(instance_id, volume_id, forced_host=None):
    '''
    Revise connection info and connector in cinder or nova.
    :param instance_id: uuid of instance.
    :param volume_id: uuid of volume.
    :return: attachment_id of connection info or zero
             which is indicative of failing to revise connection info.
    '''

    # Guarantee the volume belongs to the instance
    instance_info = get_instance_info(instance_id)
    volume_attached = instance_info['volume_attached']
    for volume in volume_attached:
        if volume_id in volume:
            logging.info('The volume %s belongs to the instance %s' %
                         (volume_id, instance_id))
            break
    else:
        logging.warning('The volume %s does not belong to the instance %s!' % (
            volume_id, instance_id))
        return 0

    # get attachment_id
    var = 'echo ' + volume_id + ' >/tmp/volume_id;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
    sql_statement = '''"SELECT * FROM nova.block_device_mapping WHERE volume_id=\\'${volume_id}\\' and deleted=0\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    pipe = " | grep -i attachment_id | sed 's/attachment_id: //'"
    res1 = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                            stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    if len(res1) > 0:
        attachment_id = res1[0].strip()
    else:
        logging.warning(
            'The attachment of volume %s in nova is NULL or all attachments in nova are deleted!' % volume_id)
        attachment_id = None
        return 0

    # get device_name
    pipe = " | grep -i device_name | sed 's/device_name: //'"
    res2 = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                            stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    device_name = res2[0].strip()

    # get connection template
    conn_info_template = find_connection_template(
        instance_id, volume_id, forced_host)
    if conn_info_template == 0:
        logging.warning(
            'Fail to revise connection info since connection_info_template is zero!')
        return 0
    nova_conn_info = conn_info_template['nova_conn_info']
    cinder_conn_info = conn_info_template['cinder_conn_info']
    cinder_connector = conn_info_template['cinder_connector']

    # take account into name id when it exists
    volume_info = get_volume_info(volume_id)
    vol_name_id = volume_info['vol_name_id']
    volume_id_bak = volume_id
    if vol_name_id == 'None':
        logging.info('The name_id of volume %s is None!' % volume_id)
    else:
        logging.info('The name_id of volume %s is %s!' %
                     (volume_id, vol_name_id))
        volume_id = vol_name_id
    # don't take accout into multiattach volume
    multiattach = volume_info['multiattach']
    if multiattach != 'False':
        logging.warning(
            'Revising operation cannot be performed since the volume %s supports multiattach!' % volume_id)
        return 0

    # revise connection info and connector in cinder and nova.
    if nova_conn_info['driver_volume_type'] == 'rbd':
        # set new parameter and revise connection info of nova
        volume_id_with_prefix = 'volume-' + volume_id
        nova_conn_info['data']['name'] = \
            re.sub('volume-.*', volume_id_with_prefix,
                   nova_conn_info['data']['name'])
        nova_conn_info['data']['volume_id'] = volume_id
        nova_conn_info['volume_id'] = volume_id
        nova_conn_info['instance'] = instance_id
        nova_conn_info['serial'] = volume_id
        connection_info = json.dumps(nova_conn_info).replace('"', '\\"')
        # update database
        var = 'echo ' + attachment_id + ' >/tmp/attachment_id;' + \
              'echo ' + '\'' + connection_info + '\'' + ' >/tmp/connection_info;'
        var_transfer = '''attachment_id=`cat /tmp/attachment_id`;connection_info=`cat /tmp/connection_info`;'''
        sql_statement = '''"UPDATE nova.block_device_mapping SET connection_info=\\'${connection_info}\\' 
        WHERE attachment_id=\\'${attachment_id}\\' and deleted=0\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        subprocess.call(cmd, shell=True, executable='/bin/bash')
        logging.info(
            'Succeed in revising connection info for attachment_id %s in nova!' % (attachment_id))

        # set new parameter and revise connection info and other information in cinder
        if forced_host == None:
            attached_host = instance_info['hostname']
        else:
            attached_host = forced_host
        mountpoint = device_name
        attach_mode = 'rw'
        attach_status = 'attached'
        cinder_conn_info['name'] = \
            re.sub('volume-.*', volume_id_with_prefix,
                   cinder_conn_info['name'])
        cinder_conn_info['volume_id'] = volume_id
        cinder_conn_info['attachment_id'] = attachment_id
        connection_info = json.dumps(cinder_conn_info).replace('"', '\\"')
        cinder_connector['mountpoint'] = device_name
        connector = json.dumps(cinder_connector).replace('"', '\\"')
        # update database
        var = 'echo ' + attachment_id + ' >/tmp/attachment_id;' + \
              'echo ' + attached_host + ' >/tmp/attached_host;' + \
              'echo ' + mountpoint + ' >/tmp/mountpoint;' + \
              'echo ' + attach_mode + ' >/tmp/attach_mode;' + \
              'echo ' + attach_status + ' >/tmp/attach_status;' + \
              'echo ' + '\'' + connection_info + '\'' + ' >/tmp/connection_info;' + \
              'echo ' + '\'' + connector + '\'' + ' >/tmp/connector;'
        var_transfer = '''attachment_id=`cat /tmp/attachment_id`;''' + \
                       '''attached_host=`cat /tmp/attached_host`;''' + \
                       '''mountpoint=`cat /tmp/mountpoint`;''' + \
                       '''attach_mode=`cat /tmp/attach_mode`;''' + \
                       '''attach_status=`cat /tmp/attach_status`;''' + \
                       '''connection_info=`cat /tmp/connection_info`;''' + \
                       '''connector=`cat /tmp/connector`;'''
        sql_statement = '''"UPDATE cinder.volume_attachment SET attached_host=\\'${attached_host}\\',''' + \
                        '''mountpoint=\\'${mountpoint}\\',''' + \
                        '''attach_mode=\\'${attach_mode}\\',''' + \
                        '''attach_status=\\'${attach_status}\\',''' + \
                        '''connection_info=\\'${connection_info}\\',''' + \
                        '''connector=\\'${connector}\\' ''' + \
                        '''WHERE id=\\'${attachment_id}\\' and deleted=0\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        subprocess.call(cmd, shell=True, executable='/bin/bash')
        logging.info(
            'Succeed in revising connection info and other information for attachment_id %s in cinder!' % (
                attachment_id))
    elif nova_conn_info['driver_volume_type'] == 'fibre_channel':
        # set new parameter and revise connection info of nova
        vol_info_from_storage = get_volume_info_from_storage(volume_id_bak)
        if 'target_lun' not in vol_info_from_storage.keys():
            logging.warning(
                'Fail to revise connection info, since %s in not in storage or the hostmap of it is None!' % volume_id)
            return 0
        else:
            target_lun = vol_info_from_storage['target_lun']
            multipath_id = vol_info_from_storage['multipath_id']
            host_name = vol_info_from_storage['host_name']
        if forced_host != None and forced_host not in host_name:
            logging.warning(
                'Forced host %s contradicts the host_name %s in storage!' % (forced_host, host_name))
            return 0
        mountpoint = device_name
        nova_conn_info['data']['target_lun'] = target_lun
        nova_conn_info['data']['volume_id'] = volume_id
        if 'targets' in nova_conn_info['data']:
            for idx in range(0, len(nova_conn_info['data']['targets'])):
                nova_conn_info['data']['targets'][idx][1] = target_lun
        if 'initiator_target_lun_map' in nova_conn_info['data']:
            for k, v in nova_conn_info['data']['initiator_target_lun_map'].items():
                for i in range(0, len(v)):
                    nova_conn_info['data']['initiator_target_lun_map'][k][i][1] = target_lun
        if 'multipath_id' in nova_conn_info['data']:
            nova_conn_info['data']['multipath_id'] = multipath_id
            device_path = '/dev/disk/by-id/dm-uuid-mpath-' + multipath_id
            nova_conn_info['data']['device_path'] = device_path
        else:
            new_lun = 'lun-' + str(target_lun)
            nova_conn_info['data']['device_path'] = re.sub(
                'lun-.*', new_lun, nova_conn_info['data']['device_path'])
        nova_conn_info['volume_id'] = volume_id
        nova_conn_info['instance'] = instance_id
        nova_conn_info['serial'] = volume_id
        connection_info = json.dumps(nova_conn_info).replace('"', '\\"')
        # update nova.bdm database
        var = 'echo ' + attachment_id + ' >/tmp/attachment_id;' + \
              'echo ' + '\'' + connection_info + '\'' + ' >/tmp/connection_info;'
        var_transfer = '''attachment_id=`cat /tmp/attachment_id`;connection_info=`cat /tmp/connection_info`;'''
        sql_statement = '''"UPDATE nova.block_device_mapping SET connection_info=\\'${connection_info}\\' 
        WHERE attachment_id=\\'${attachment_id}\\' and deleted=0\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        subprocess.call(cmd, shell=True, executable='/bin/bash')
        logging.info(
            'Succeed in revising connection info for attachment_id %s in nova!' % (attachment_id))

        # set new parameter and revise connection info and other information in cinder
        if forced_host == None:
            attached_host = instance_info['hostname']
        else:
            attached_host = forced_host
        mountpoint = device_name
        attach_mode = 'rw'
        attach_status = 'attached'
        cinder_conn_info['target_lun'] = target_lun
        cinder_conn_info['volume_id'] = volume_id
        cinder_conn_info['attachment_id'] = attachment_id
        connection_info = json.dumps(cinder_conn_info).replace('"', '\\"')
        cinder_connector['mountpoint'] = device_name
        connector = json.dumps(cinder_connector).replace('"', '\\"')
        # update cinder.volume_attachment database
        var = 'echo ' + attachment_id + ' >/tmp/attachment_id;' + \
              'echo ' + attached_host + ' >/tmp/attached_host;' + \
              'echo ' + mountpoint + ' >/tmp/mountpoint;' + \
              'echo ' + attach_mode + ' >/tmp/attach_mode;' + \
              'echo ' + attach_status + ' >/tmp/attach_status;' + \
              'echo ' + '\'' + connection_info + '\'' + ' >/tmp/connection_info;' + \
              'echo ' + '\'' + connector + '\'' + ' >/tmp/connector;'
        var_transfer = '''attachment_id=`cat /tmp/attachment_id`;''' + \
                       '''attached_host=`cat /tmp/attached_host`;''' + \
                       '''mountpoint=`cat /tmp/mountpoint`;''' + \
                       '''attach_mode=`cat /tmp/attach_mode`;''' + \
                       '''attach_status=`cat /tmp/attach_status`;''' + \
                       '''connection_info=`cat /tmp/connection_info`;''' + \
                       '''connector=`cat /tmp/connector`;'''
        sql_statement = '''"UPDATE cinder.volume_attachment SET attached_host=\\'${attached_host}\\',''' + \
                        '''mountpoint=\\'${mountpoint}\\',''' + \
                        '''attach_mode=\\'${attach_mode}\\',''' + \
                        '''attach_status=\\'${attach_status}\\',''' + \
                        '''connection_info=\\'${connection_info}\\',''' + \
                        '''connector=\\'${connector}\\' ''' + \
                        '''WHERE id=\\'${attachment_id}\\' and deleted=0\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        subprocess.call(cmd, shell=True, executable='/bin/bash')
        logging.info(
            'Succeed in revising connection info and other information for attachment_id %s in cinder!' % attachment_id)
    else:
        logging.warning(
            'Can only process volume of ceph or fibre channel type!')
        return 0

    # revise host information in nova.instances
    if forced_host is not None and instance_info['hostname'] != forced_host:
        cmd = "openstack hypervisor list | grep " + \
              forced_host + " | awk '{print $4}'"
        res = execute_openstack_cmd(cmd)
        if len(res) > 0:
            node = res[0].strip()
        else:
            logging.warning(
                'Fail to get hypervisor name for host %s!' % forced_host)
            return 0
        var = 'echo ' + forced_host + ' >/tmp/host;' + \
              'echo ' + node + ' >/tmp/node;' + \
              'echo ' + instance_id + ' >/tmp/instance_id;'
        var_transfer = '''host=`cat /tmp/host`;''' + \
                       '''node=`cat /tmp/node`;''' + \
                       '''instance_id=`cat /tmp/instance_id`;'''
        sql_statement = '''"UPDATE nova.instances SET host=\\'${host}\\',''' + \
                        '''node=\\'${node}\\' ''' + \
                        '''WHERE uuid=\\'${instance_id}\\'\G"'''
        cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
              '''"''' + var + '''"''' + \
              ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
              '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
              sql_statement + '''\''''
        subprocess.call(cmd, shell=True, executable='/bin/bash')
        logging.info('Revise host %s to %s for instance %s!' %
                     (instance_info['hostname'], forced_host, instance_id))

    return attachment_id


def set_multiattach_to_true(volume_id):
    '''
    Set multiattach to true for specified volume.
    This operation only need to be performed after
    setting multiattach to false by hand in order
    to reinstate instances and volumes.

    :param volume_id: uuid of volume.
    :return: 0 is indicative of failure.
    '''

    volume_info = get_volume_info(volume_id)
    multiattach = volume_info['multiattach']
    if multiattach == 'True':
        logging.warning(
            'Fail to set multiattach to True since the multiattach of volume %s is True' % volume_id)
        return 0

    var = 'echo ' + volume_id + ' >/tmp/volume_id;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
    sql_statement = '''"UPDATE cinder.volumes SET multiattach=1 WHERE id=\\'${volume_id}\\' and deleted=0\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    subprocess.call(cmd, shell=True, executable='/bin/bash')

    volume_info = get_volume_info(volume_id)
    multiattach = volume_info['multiattach']
    if multiattach == 'True':
        logging.info(
            'Succeed in setting multiattach to True for volume %s' % volume_id)
        return volume_id
    else:
        logging.warning('Encounter some abnormal problems!')
        return 0


def set_multiattach_to_false(volume_id):
    '''
    Only when bdm number of specified volume is below one,
    can multiattach property of it be set to False.

    :param volume_id: uuid of volume.
    :return: 0 is indicative of failure.
    '''

    volume_info = get_volume_info(volume_id)
    multiattach = volume_info['multiattach']
    if multiattach == 'False':
        logging.warning(
            'Fail to set multiattach to False since the multiattach of volume %s is False' % volume_id)
        return 0

    # ensure bdm number of specified volume is below one
    var = 'echo ' + volume_id + ' >/tmp/volume_id;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
    sql_statement = '''"SELECT * FROM nova.block_device_mapping WHERE volume_id=\\'${volume_id}\\' and deleted=0\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    pipe = " | grep -i attachment_id | sed 's/attachment_id: //'"
    res = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                           stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    if len(res) > 1:
        logging.warning('Cannot set multiattach property to False since the attachments'
                        ' of volume %s in nova.bdm are above one, ie, %s' % (volume_id, len(res)))
        return 0
    logging.info('The attachments number of volume %s in nova.bdm is %s' %
                 (volume_id, len(res)))

    var = 'echo ' + volume_id + ' >/tmp/volume_id;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
    sql_statement = '''"UPDATE cinder.volumes SET multiattach=0 WHERE id=\\'${volume_id}\\' and deleted=0\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    subprocess.call(cmd, shell=True, executable='/bin/bash')

    volume_info = get_volume_info(volume_id)
    multiattach = volume_info['multiattach']
    if multiattach == 'False':
        logging.info(
            'Succeed in setting multiattach to False for volume %s' % volume_id)
        return volume_id
    else:
        logging.warning('Encounter some abnormal problems!')
        return 0


def set_volume_state(instance_id):
    '''
    Set in-use state for all volumes attached to the server.
    :param instance_id: uuid of instance
    :return: uuid of instance
    '''

    instance_info = get_instance_info(instance_id)
    volume_attached = instance_info['volume_attached']
    for volume_id in volume_attached:
        cmd = 'openstack volume set --state in-use ' + volume_id
        res = execute_openstack_cmd(cmd)
    logging.info('Succeed in setting in-use state for volumes %s of server %s' %
                 (volume_attached, instance_id))

    return instance_id


def swap_volume_information_for_retype_hang(volume_id):
    '''
    Swap volume information between original volume and new volume if
    retype operation has hung and new volume has been used. In addition,
    can only process retype hang issues when new volume type is rbd or fc!

    :param volume_id: uuid of volume which hangs in retyping state.
    :return: uuid of new volume or zero
             which is indicative of failing to swap volume information.
    '''

    # get new volume info
    migration_status = 'target:' + volume_id
    var = 'echo ' + migration_status + ' >/tmp/migration_status;'
    var_transfer = '''migration_status=`cat /tmp/migration_status`;'''
    sql_statement = '''"SELECT * FROM cinder.volumes WHERE migration_status=\\'${migration_status}\\'\G"'''
    cmd = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
          '''"''' + var + '''"''' + \
          ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
          '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
          sql_statement + '''\''''
    pipe = " | egrep '  id:|  host:|  volume_type_id:|  service_uuid:' | sed 's/.*: //g'"
    res1 = subprocess.Popen(cmd + pipe, shell=True, executable='/bin/bash',
                            stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    if len(res1) > 0:
        new_volume_id = res1[0].strip()
        new_volume_host = res1[1].strip()
        new_volume_volume_type_id = res1[2].strip()
        new_volume_service_uuid = res1[3].strip()
        logging.info(
            'The information of new volume is %s' % {'new_volume_id': new_volume_id, 'new_volume_host': new_volume_host,
                                                     'new_volume_volume_type_id': new_volume_volume_type_id,
                                                     'new_volume_service_uuid': new_volume_service_uuid})
    else:
        logging.warning(
            'There is not a new volume during retype operation of volume %s' % volume_id)
        return 0

    # get original volume info
    var = 'echo ' + volume_id + ' >/tmp/volume_id;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
    sql_statement = '''"SELECT * FROM cinder.volumes WHERE id=\\'${volume_id}\\'\G"'''
    cmd2 = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
           '''"''' + var + '''"''' + \
           ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
           '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
           sql_statement + '''\''''
    pipe2 = " | egrep '  host:|  volume_type_id:|  migration_status:|  service_uuid:' | sed 's/.*: //g'"
    res2 = subprocess.Popen(cmd2 + pipe2, shell=True, executable='/bin/bash',
                            stdout=subprocess.PIPE, encoding='utf8').stdout.readlines()
    if len(res2) > 0:
        org_volume_host = res2[0].strip()
        org_volume_volume_type_id = res2[1].strip()
        org_volume_migration_status = res2[2].strip()
        org_volume_service_uuid = res2[3].strip()
        logging.info(
            'The information of original volume is %s' % {'volume_id': volume_id, 'org_volume_host': org_volume_host,
                                                          'org_volume_volume_type_id': org_volume_volume_type_id,
                                                          'org_volume_service_uuid': org_volume_service_uuid})
    else:
        logging.warning('Can not find volume %s information!' % volume_id)
        return 0

    volume_info = get_volume_info(volume_id)
    multiattach = volume_info['multiattach']
    if multiattach != 'False':
        logging.warning(
            'Revising operation cannot be performed since the volume %s supports multiattach!' % volume_id)
        return 0
    vol_name_id = volume_info['vol_name_id']
    server_id = volume_info['server_id']
    host_name = volume_info['host_name']
    if server_id is None or host_name is None:
        logging.warning(
            'Can not acquire server_id or host_name according to volume %s, stop revising!' % volume_id)
        return 0

    # ensure retype operation has hung and new volume bas been utilized.
    block_info = get_block_info(volume_id)
    # need to take account into properties field if new volume belongs to as5600 type
    new_vol_is_as5600 = False
    if 'json' in block_info:
        json_part = re.sub('.*json:', '', block_info).replace(' (raw)', '')
        block_dict = json.loads(json_part)
        real_volume_id = block_dict['file']['image'].replace('volume-', '')
        if real_volume_id != volume_id and real_volume_id != vol_name_id and real_volume_id == new_volume_id:
            logging.info(
                'Instance has utilized new volume %s, but database information between original volume %s and new '
                'volume %s has not been swapped!' % (new_volume_id, volume_id, new_volume_id))
        else:
            logging.warning(
                'The database information of volume %s complies to the fact!' % volume_id)
            return 0
        # determine eligible cinder-volume pod in order to execute rbd command
        var = 'echo ' + new_volume_host + ' >/tmp/vol_host;'
        var_transfer = '''vol_host=`cat /tmp/vol_host`;'''
        sql_statement = '''"SELECT * FROM cinder.volumes WHERE host=\\'${vol_host}\\' and deleted=0 LIMIT 1 OFFSET 0\G"'''
        cmd3 = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
               '''"''' + var + '''"''' + \
               ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
               '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
               sql_statement + '''\''''
        pipe3 = " | grep '   id:' | awk 'FS=\":\" {print $2}'"
        res3 = subprocess.Popen(cmd3 + pipe3, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                                encoding='utf8').stdout.readlines()
        vol_sec = res3[0].strip()
        storage_info = get_storage_info(vol_sec)
        if storage_info['volume_driver'] != 'ceph':
            logging.warning(
                'The selected volume %s does not belong to rbd type!' % vol_sec)
            return 0
        volume_pod = storage_info['volume_pod']
        rbd_ceph_conf = storage_info['rbd_ceph_conf']
        rbd_user = storage_info['rbd_user']
        rbd_pool = storage_info['rbd_pool']
        volume_name_in_ceph = rbd_pool + '/volume-' + new_volume_id
        # execute rbd du command
        cmd4 = "kubectl  exec -it -n openstack " + volume_pod + " -- rbd --conf " + rbd_ceph_conf + \
               " --user " + rbd_user + " du " + volume_name_in_ceph
        pipe4 = " | grep 'GiB'"
        res4 = subprocess.Popen(cmd4 + pipe4, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                                encoding='utf8').stdout.readlines()
        if len(res4) != 1:
            logging.warning('Command has Error：The result of command %s in pod %s is %s' % (
                cmd4, volume_pod, res4))
            return 0
        logging.info('The result of command %s in pod %s is %s' %
                     (cmd4, volume_pod, res4))
        # compare provisioned capacity and used capacity to determine whether copy is done
        ceph_du = res4[0].strip().split()
        if ceph_du[1] != ceph_du[2]:
            logging.warning('The provisioned capacity is %s and the used capacity is %s' % (
                ceph_du[1], ceph_du[2]))
            return 0
        logging.info(
            'The provisioned capacity is the same as the used capacity and the value is %s. Therefore, copy between volume %s and'
            ' new volume %s is done' % (ceph_du[1], volume_id, new_volume_id))
    elif '/dev/disk/by-id/' in block_info:
        uuid = re.sub('.*mpath-', '', block_info).replace(' (raw)', '')
        new_vol_info_from_storage = get_volume_info_from_storage(new_volume_id)
        if new_vol_info_from_storage == {}:
            logging.warning(
                'Cannot acquire multipath_id from storage for volume %s' % new_volume_id)
            return 0
        if uuid != new_vol_info_from_storage['multipath_id']:
            logging.warning('The new volume %s has not been used according to uuid %s' % (
                new_volume_id, uuid))
            return 0
        logging.info('The new volume %s has been utilized according to uuid %s' % (
            new_volume_id, uuid))
        if 'lun_group_name' in new_vol_info_from_storage:
            logging.info('The new volume %s belongs to as5600 type!' %
                         new_volume_id)
            new_vol_is_as5600 = True
    else:
        logging.warning('Can not parsing block info %s' % block_info)
        return 0

    # need to unmap volume from host for fibre channel type for old volume
    old_vol_is_fc = False
    org_storage_info = get_storage_info(volume_id)
    if org_storage_info['volume_driver'] == 'as5600' or org_storage_info['volume_driver'] == 'g2/g5':
        old_vol_is_fc = True
        logging.info('The original volume %s belongs to fc type!' % volume_id)

    # need to take account into provider_location field if new volume belongs to as5600 type
    if new_vol_is_as5600:
        # get provider location of new volume
        migration_status = 'target:' + volume_id
        var = 'echo ' + migration_status + ' >/tmp/migration_status;'
        var_transfer = '''migration_status=`cat /tmp/migration_status`;'''
        sql_statement = '''"SELECT * FROM cinder.volumes WHERE migration_status=\\'${migration_status}\\'\G"'''
        cmd5 = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
               '''"''' + var + '''"''' + \
               ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
               '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
               sql_statement + '''\''''
        pipe5 = " | egrep '  provider_location:' | sed 's/provider_location: //g'"
        res5 = subprocess.Popen(cmd5 + pipe5, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                                encoding='utf8').stdout.readlines()
        if len(res5) > 0 and res5[0].strip() != 'NULL':
            # "{'classname': 'FUJITSU_StorageVolume', 'keybindings': {'SystemName': 'fe80::200:e50:da89:ee00', 'DeviceID': '600000E00D2A0000002A09EE014C0000'}, 'vol_name': 'FJosv_a8Gqnf-wH6UP3WjzbhMbBQ=='}"
            new_provider_location = res5[0].strip()
            logging.info('The provider_location of new volume %s is %s' %
                         (new_volume_id, new_provider_location))
        else:
            logging.warning(
                'Can not find provider_location of volume %s!' % new_volume_id)
            return 0

        # get provider location of original volume
        var = 'echo ' + volume_id + ' >/tmp/volume_id;'
        var_transfer = '''volume_id=`cat /tmp/volume_id`;'''
        sql_statement = '''"SELECT * FROM cinder.volumes WHERE id=\\'${volume_id}\\'\G"'''
        cmd6 = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
               '''"''' + var + '''"''' + \
               ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
               '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
               sql_statement + '''\''''
        pipe6 = " | egrep '  provider_location:' | sed 's/provider_location: //g'"
        res6 = subprocess.Popen(cmd6 + pipe6, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                                encoding='utf8').stdout.readlines()
        if len(res6) > 0 and res6[0].strip() != 'NULL':
            # "{'classname': u'FUJITSU_StorageVolume', 'keybindings': {'SystemName': u'fe80::200:e50:da8b:a200', 'DeviceID': u'600000E00D2A0000002A0BA200400000'}, 'vol_name': u'FJosv_Bo6jujdu_ubwH8xeBRkVTw=='}"
            org_provider_location = res6[0].strip()
            logging.info('The provider_location of original volume %s is %s' % (
                volume_id, org_provider_location))
        else:
            logging.warning(
                'Can not find provider_location of volume %s!' % volume_id)
            return 0

        # swap provider location between new volume and original volume
        new_storage_info = get_storage_info(new_volume_id)
        volume_pod = new_storage_info['volume_pod']
        # retrieve database connection
        cmd7 = "kubectl exec -it -n openstack " + volume_pod + \
               " -- cat /etc/cinder/cinder.conf | grep -i 'connection =' | sed 's/connection = //g'"
        db_connection = os.popen(cmd7).readlines()[0].strip()
        # set org_provider_location for new volume
        os.system('ls /tmp/swap_location 2>/dev/null && rm /tmp/swap_location')
        os.system('touch /tmp/swap_location')
        f = open('/tmp/swap_location', 'a')
        script1 = 'from sqlalchemy import create_engine' + '\n'
        f.write(script1)
        script2 = "engine = create_engine('" + db_connection + "')" + '\n'
        f.write(script2)
        script3 = "temp='''" + org_provider_location + "'''" + '\n'
        f.write(script3)
        script4 = "mysql_cmd = '''update cinder.volumes set provider_location='''" + " + '''" + '''"''' + "'''" + "+ temp" + \
                  " + '''" + '''"''' + "'''" + " + ''' where migration_status=\'" + \
                  migration_status + "\' '''" + '\n'
        f.write(script4)
        script5 = "engine.execute(mysql_cmd)" + '\n'
        f.write(script5)
        f.close()
        cmd8 = "kubectl cp -n openstack /tmp/swap_location " + \
               volume_pod + ":/tmp/swap_location"
        subprocess.call(cmd8, shell=True, executable='/bin/bash')
        cmd9 = "kubectl exec -it -n openstack " + \
               volume_pod + " -- python3 /tmp/swap_location"
        subprocess.call(cmd9, shell=True, executable='/bin/bash')
        logging.info(
            'Succeed in setting original provider_location for new volume %s' % new_volume_id)
        os.system('rm /tmp/swap_location')
        # set new_provider_location for original volume
        os.system('ls /tmp/swap_location 2>/dev/null && rm /tmp/swap_location')
        os.system('touch /tmp/swap_location')
        f = open('/tmp/swap_location', 'a')
        script1 = 'from sqlalchemy import create_engine' + '\n'
        f.write(script1)
        script2 = "engine = create_engine('" + db_connection + "')" + '\n'
        f.write(script2)
        script3 = "temp='''" + new_provider_location + "'''" + '\n'
        f.write(script3)
        script4 = "mysql_cmd = '''update cinder.volumes set provider_location='''" + " + '''" + '''"''' + "'''" + "+ temp" + \
                  " + '''" + '''"''' + "'''" + " + ''' where id=\'" + volume_id + "\' '''" + '\n'
        f.write(script4)
        script5 = "engine.execute(mysql_cmd)" + '\n'
        f.write(script5)
        f.close()
        cmd8 = "kubectl cp -n openstack /tmp/swap_location " + \
               volume_pod + ":/tmp/swap_location"
        subprocess.call(cmd8, shell=True, executable='/bin/bash')
        cmd9 = "kubectl exec -it -n openstack " + \
               volume_pod + " -- python3 /tmp/swap_location"
        subprocess.call(cmd9, shell=True, executable='/bin/bash')
        logging.info(
            'Succeed in setting new provider_location for original volume %s' % volume_id)
        os.system('rm /tmp/swap_location')

    # swap information between new volume and original volume
    var = 'echo ' + volume_id + ' >/tmp/volume_id;' + \
          'echo ' + org_volume_host + ' >/tmp/org_volume_host;' + \
          'echo ' + org_volume_volume_type_id + ' >/tmp/org_volume_volume_type_id;' + \
          'echo ' + org_volume_service_uuid + ' >/tmp/org_volume_service_uuid;' + \
          'echo ' + new_volume_id + ' >/tmp/new_volume_id;' + \
          'echo ' + new_volume_host + ' >/tmp/new_volume_host;' + \
          'echo ' + new_volume_volume_type_id + ' >/tmp/new_volume_volume_type_id;' + \
          'echo ' + new_volume_service_uuid + ' >/tmp/new_volume_service_uuid;'
    var_transfer = '''volume_id=`cat /tmp/volume_id`;''' + \
                   '''org_volume_host=`cat /tmp/org_volume_host`;''' + \
                   '''org_volume_volume_type_id=`cat /tmp/org_volume_volume_type_id`;''' + \
                   '''org_volume_service_uuid=`cat /tmp/org_volume_service_uuid`;''' + \
                   '''new_volume_id=`cat /tmp/new_volume_id`;''' + \
                   '''new_volume_host=`cat /tmp/new_volume_host`;''' + \
                   '''new_volume_volume_type_id=`cat /tmp/new_volume_volume_type_id`;''' + \
                   '''new_volume_service_uuid=`cat /tmp/new_volume_service_uuid`;'''
    sql_statement1 = '''"UPDATE cinder.volumes SET host=\\'${new_volume_host}\\',''' + \
                     '''volume_type_id=\\'${new_volume_volume_type_id}\\',''' + \
                     '''migration_status=\\'success\\',''' + \
                     '''service_uuid=\\'${new_volume_service_uuid}\\',''' + \
                     '''_name_id=\\'${new_volume_id}\\' ''' + \
                     '''WHERE id=\\'${volume_id}\\'\G"'''
    sql_statement2 = '''"UPDATE cinder.volumes SET host=\\'${org_volume_host}\\',''' + \
                     '''volume_type_id=\\'${org_volume_volume_type_id}\\',''' + \
                     '''migration_status=NULL,''' + \
                     '''service_uuid=\\'${org_volume_service_uuid}\\',''' + \
                     '''_name_id=\\'${volume_id}\\' ''' + \
                     '''WHERE id=\\'${new_volume_id}\\'\G"'''
    cmd1 = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
           '''"''' + var + '''"''' + \
           ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
           '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
           sql_statement1 + '''\''''
    cmd2 = '''kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + \
           '''"''' + var + '''"''' + \
           ''';kubectl exec -it -n openstack mariadb-server-0 -c mariadb -- bash -c ''' + '''$\'''' + var_transfer + \
           '''mysql -uroot -p$(env | grep MYSQL_DBADMIN_PASSWORD | cut -d \\'=\\' -f 2) -e ''' + \
           sql_statement2 + '''\''''
    subprocess.call(cmd1, shell=True, executable='/bin/bash')
    subprocess.call(cmd2, shell=True, executable='/bin/bash')
    logging.info('Succeed in swapping information between original volume %s and new volume %s' % (
        volume_id, new_volume_id))

    # swap properties between new volume and original volume
    cmd10 = 'openstack volume show ' + volume_id + ' -f value -c properties'
    res10 = execute_openstack_cmd(cmd10)
    org_properties_list = res10[0].strip().split(', ')
    org_properties = {}
    if '=' in org_properties_list[0]:
        for i in org_properties_list:
            if '==' in i:
                k = 'FJ_Volume_Name'
                v = i.split('Name=')[1].strip("'")
                org_properties[k] = v
                continue
            k = i.split('=')[0]
            v = i.split('=')[1].strip("'")
            org_properties[k] = v
    elif org_properties_list[0] == '':
        logging.info('The properties of volume %s is empty' % volume_id)
    else:
        logging.warning('Can not parse properties of volume %s' % volume_id)
        return 0
    cmd11 = 'openstack volume show ' + new_volume_id + ' -f value -c properties'
    res11 = execute_openstack_cmd(cmd11)
    new_properties_list = res11[0].strip().split(', ')
    new_properties = {}
    if '=' in new_properties_list[0]:
        for i in new_properties_list:
            if '==' in i:
                k = 'FJ_Volume_Name'
                v = i.split('Name=')[1].strip("'")
                new_properties[k] = v
                continue
            k = i.split('=')[0]
            v = i.split('=')[1].strip("'")
            new_properties[k] = v
    elif new_properties_list[0] == '':
        logging.info('The properties of volume %s is empty' % new_volume_id)
    else:
        logging.warning('Can not parse properties of volume %s' %
                        new_volume_id)
        return 0
    cmd12 = 'openstack volume set'
    for org_k, org_v in org_properties.items():
        cmd12 += ' --property ' + org_k + '=' + "'" + org_v + "'"
    execute_openstack_cmd(cmd12 + " " + new_volume_id)
    logging.info(
        'Succeed in setting original properties for new volume %s' % new_volume_id)
    cmd13 = 'openstack volume set'
    for new_k, new_v in new_properties.items():
        cmd13 += ' --property ' + new_k + '=' + "'" + new_v + "'"
    execute_openstack_cmd(cmd13 + " " + volume_id)
    logging.info(
        'Succeed in setting new properties for original volume %s' % volume_id)

    # revise connection_info in nova and cinder
    res = revise_connection_info(server_id, volume_id)
    if res == 0:
        logging.warning('Fail to revise connection_info in nova and cinder!')
        return 0

    if old_vol_is_fc:
        res = unmap_volume_from_host(new_volume_id, host_name)
        if res == 0:
            logging.warning('Fail to unmap volume %s from host %s!' %
                            (new_volume_id, host_name))
        logging.info('Succeed in unmapping volume %s from host %s!' %
                     (new_volume_id, host_name))

    return new_volume_id


def main():
    print('''
    支持进行的操作：
    1. 查看卷的存储后端信息，如存储类型、存储ip、存储用户名等
    2. 查看g2卷/as5600卷在存储上的映射情况：映射给哪个计算节点，映射的target_lun等
    3. 查看指定计算节点的hba卡信息
    4. 查看三个mariadb-server的数据是否一致
    5. 查看as5600卷在存储上的名称
    6. 查看卷在nova和cinder数据库中的挂载信息
    7. 查看卷在qemu中对应的磁盘信息(有时libvirt中查看的磁盘信息并不准确)
    8. 从fc san存储上将卷映射到指定的计算节点上(映射到虚机前提是先映射到虚机所在的节点上)
    9. 修复resize/migrate/evacuate/rebuild操作失败后卷在cinder、nova中的信息
    10. 修复nova中attachment_id为NULL及非多挂载卷在cinder中有多条attachment的问题
    11. 确认卷的retype操作是否已经开始，如果开始则输出老卷和新卷的信息
    12. 修复retype操作hang死后卷在cinder、nova中的信息
    13. 修复卷类型是None的问题
    14. 更改指定虚机的所有卷状态为in-use
    15. 修改卷的multiattach属性为False(确保卷只挂载到一个虚机上)
    16. 修改卷的multiattach属性为True
    99. 调试程序(开发人员使用)

    程序运行的日志文件是：/var/log/reinstate_health.log
    ''')
    idx = input('请输入要执行的操作序号：')
    try:
        if int(idx) == 1:
            volume_id = input('请输入卷id：')
            storage_info = get_storage_info(volume_id)
            if storage_info == {}:
                print('无法查看卷的存储后端信息，请查看日志分析原因！')
            else:
                print('卷%s的存储后端信息是：%s' % (volume_id, storage_info))
        elif int(idx) == 2:
            volume_id = input('请输入卷id：')
            res2 = get_volume_info_from_storage(volume_id)
            if res2 == {}:
                print('映射不存在或者查看映射失败，请查看日志分析原因！')
            else:
                print('卷%s在存储上的映射情况是%s' % (volume_id, res2))
        elif int(idx) == 3:
            hostname = input('请输入计算节点名称：')
            if not validate_forced_host(hostname):
                print('请输入合法的host名称！')
            else:
                res3 = get_hba_port(hostname)
                if res3 == 0:
                    print('无法获得hba卡信息，请查看日志分析原因！')
                else:
                    print('节点%s的hba卡的wwpn号及状态是: %s' % (hostname, res3))
        elif int(idx) == 4:
            volume_id = input('请随机输入一个in-use状态的卷id：')
            if validate_three_pod_consistency(volume_id):
                print('三个mariadb-server pod的数据是一致的')
            else:
                print('三个mariadb-server pod的数据是不一致的，请进行修复！')
        elif int(idx) == 5:
            volume_id = input('请输入一个as5600类型卷id：')
            res5 = get_as5600_FJ_info(volume_id)
            if res5 == 0:
                print('查看失败，请查看日志分析原因！')
            else:
                print(res5)
        elif int(idx) == 6:
            volume_id = input('请输入卷id：')
            res6 = get_connection_info(volume_id)
            if res6 == 0:
                print('没有在nova、cinder中查看到完整的attachment信息，请查看日志分析原因！')
            elif res6 == 'many':
                print('异常：nova中包含卷%s的多条attachment信息' % volume_id)
        elif int(idx) == 7:
            volume_id = input('请输入卷id：')
            res7 = get_block_info(volume_id)
            if res7 == 0:
                print('卷在qemu中对应的磁盘信息无法获取，请查看日志分析原因！')
            else:
                print('卷%s在qemu中对应的磁盘信息是：\n%s' % (volume_id, res7))
        elif int(idx) == 8:
            volume_id = input('请输入卷id：')
            host_name = input('请输入要映射到的计算节点：')
            res8 = map_volume_to_host(volume_id, host_name)
            if res8 == 0:
                print('映射失败，请查看日志分析原因！')
            else:
                print('映射成功，卷%s在存储上的映射情况是: %s' % (volume_id, res8))
        elif int(idx) == 9:
            instance_id = input('请输入虚机id：')
            volume_id = input('请输入卷id：')
            forced_host_request = input(
                '是否强制指定虚机要恢复到的计算节点，若不指定采用当前虚机的host(Yes/No)：')
            if forced_host_request.lower() == 'yes':
                forced_host = input('请输入指定的计算节点：')
                if not validate_forced_host(forced_host):
                    print('请输入合法的host名称！')
                else:
                    res9 = revise_connection_info(
                        instance_id, volume_id, forced_host)
            elif forced_host_request.lower() == 'no':
                res9 = revise_connection_info(instance_id, volume_id)
            else:
                print('输入的指令无法识别，请重新运行程序')
                res9 = 0
            if res9 == 0:
                print('修复失败，指令输入错误或需查看日志分析失败原因！')
            else:
                print('修复成功，请查看卷在nova和cinder数据库中的挂载信息')
        elif int(idx) == 10:
            volume_id = input('请输入卷id：')
            res10 = ensure_attachment_num_and_relation(volume_id)
            if res10 == 0:
                print('修复失败，请查看日志分析具体原因！')
            else:
                print('修复成功，请查看卷在nova和cinder数据库中的挂载信息')
        elif int(idx) == 11:
            volume_id = input('请输入卷id：')
            res11 = has_retype_operation(volume_id)
            if res11:
                print('卷%s正在进行retype操作，新卷和老卷信息如上所示！' % volume_id)
            else:
                print('卷%s的retype操作没有开始！' % volume_id)
        elif int(idx) == 12:
            volume_id = input('请输入卷id：')
            res12 = swap_volume_information_for_retype_hang(volume_id)
            if res12 == 0:
                print('retype操作修复失败，请查看日志分析原因！')
            else:
                print('修复成功，请用openstack volume show %s查看卷的信息' % volume_id)
                print('并查看卷%s在nova和cinder数据库中的挂载信息' % volume_id)
                print('此外，需要将临时卷%s删除(若已删除，则不用继续操作)' % res12)
        elif int(idx) == 13:
            volume_id = input('请输入卷id：')
            res13 = revise_none_type(volume_id)
            if res13 == 0:
                print('修复失败，请查看日志分析原因！')
            else:
                print('修复成功，请查看卷的类型')
        elif int(idx) == 14:
            instance_id = input('请输入虚机id：')
            set_volume_state(instance_id)
            print('修改完毕，请查看该虚机上卷的状态！')
        elif int(idx) == 15:
            volume_id = input('请输入卷id：')
            res15 = set_multiattach_to_false(volume_id)
            if res15 == 0:
                print('修改失败，请查看日志分析原因！')
            else:
                print('修改完毕，请查看卷%s的multiattach属性！' % volume_id)
        elif int(idx) == 16:
            volume_id = input('请输入卷id：')
            res16 = set_multiattach_to_true(volume_id)
            if res16 == 0:
                print('修改失败，请查看日志分析原因！')
            else:
                print('修改完毕，请查看卷%s的multiattach属性！' % volume_id)
        elif int(idx) == 99:
            # instance_id = '51730520-f8f4-486a-a2e9-ad2932547e11'
            pass
        else:
            print('输入的操作序号无法识别，请重新运行程序')
    except:
        print('程序运行失败，请输入合法的操作序号如：1')


if __name__ == '__main__':
    main()
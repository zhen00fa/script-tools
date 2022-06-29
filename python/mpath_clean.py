#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
This python script aims at pruning redundant
disk paths of fibre channel volumes. See specifc
operations in the /var/log/mpathlog.
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor
from oslo_service import periodic_task
from nova import utils


class MultiPathClean(object):
    """clean redundant fiber channel device."""

    def __init__(self):
        pass

    def _run_multipath(self, multipath_command, **kwargs):
        check_exit_code = kwargs.pop('check_exit_code', 0)
        (out, err) = utils.execute('multipath',
                                   *multipath_command,
                                   run_as_root=True,
                                   check_exit_code=check_exit_code)
        print("multipath %(command)s: stdout=%(out)s stderr=%(err)s"
              % {'command': multipath_command, 'out': out, 'err': err})

        return out, err
    pass


try:

    logging.basicConfig(filename='/var/log/mpathlog', format='%(asctime)s %(name)s: %(levelname)s %(message)s', \
                        level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
    # it suggests that the script is running
    logging.info('The redundant disk paths of fibre channel volumes are monitored!')

    # check required software
    temp = os.popen('/usr/bin/which /sbin/multipath')
    if temp.read() == '':
        # print log information
        logging.warning('Please install multipath-tools software in order to be able to use this script!')
    else:
        pass


    def dmap_reload(path):
        sd_loc = path.find('sd')
        # There may be disk path like "sdaa", so we separate it from its following whitespace.
        sd_loc_end = path.find(' ', sd_loc)
        if '-fc-' in os.popen('udevadm info /dev/' + path[sd_loc:sd_loc_end] + ' | grep ID_PATH_TAG | grep fc').read():
            os.system('multipath -r /dev/' + path[sd_loc:sd_loc_end])
            logging.debug('force reload %s' % path[sd_loc:sd_loc_end])


    def del_faildev(fail):
        sd_loc = fail.find('sd')
        # There may be disk path like "sdaa", so we separate it from its following whitespace.
        sd_loc_end = fail.find(' ', sd_loc)
        if '-fc-' in os.popen('udevadm info /dev/' + fail[sd_loc:sd_loc_end] + ' | grep ID_PATH_TAG | grep fc').read():
            os.system('blockdev --flushbufs /dev/' + fail[sd_loc:sd_loc_end])
            os.system('echo 1 > /sys/block/' + fail[sd_loc:sd_loc_end] + '/device/delete')
            # print log information
            logging.debug('delete failed device %s' % fail[sd_loc:sd_loc_end])


    def del_map(uuid):
        if uuid[:4] == '3600':
            map = uuid[:33]
        elif uuid[:4] == 'mpat':
            map_loc_end = uuid.find(' ', 0)
            map = uuid[0:map_loc_end]
        os.system('/sbin/dmsetup suspend /dev/mapper/' + map)
        os.system('/sbin/dmsetup clear /dev/mapper/' + map)
        os.system('/sbin/dmsetup wipe_table /dev/mapper/' + map)
        os.system('/sbin/multipath -f /dev/mapper/' + map)
        os.system('/sbin/dmsetup remove /dev/mapper/' + map)
        # print log information
        logging.debug('delete useless multipath mapper %s' % map)


    # force orphan devmap reload
    os.system('/sbin/multipathd show paths > /root/pathfile')
    with open('/root/pathfile') as f:
        L = f.readlines()
    for i in L:
        if 'orphan' in i:
            dmap_reload(i)
        else:
            pass
    os.system('sleep 2')

    # delete failed device
    os.system('/sbin/multipath -ll > /root/pathfile')
    with open('/root/pathfile') as f:
        L = f.readlines()
    with ThreadPoolExecutor(max_workers=5) as executor:
        for i in L:
            if 'failed' in i:
                executor.submit(del_faildev, i)
            else:
                pass
    os.system('sleep 2')

    # delete redundant /sbin/multipath mapper
    os.system('/sbin/multipath -ll > /root/pathfile')
    with open('/root/pathfile') as f:
        L = f.readlines()
    L_uuid = []
    L_uuid_idx = []
    for i in L:
        if i[:4] == '3600' or i[:4] == 'mpat':
            L_uuid.append(i)
            L_uuid_idx.append(L.index(i))
        else:
            pass
    for x, y in zip(L_uuid_idx, L_uuid_idx[1:]):
        if y - x == 2:
            del_map(L[x])

    # when the redundant multipath mapper is founded at the end of L_uuid_idx, that is L_uuid_idx[-1]，we should delete one more.
    if len(L_uuid_idx) > 0 and L_uuid_idx[-1] == len(L) - 2:
        del_map(L_uuid[-1])

    # delete orphan path which can not reload
    os.system('/sbin/multipathd show paths > /root/pathfile')
    with open('/root/pathfile') as f:
        L = f.readlines()
    for i in L:
        if 'orphan' in i:
            del_faildev(i)
        else:
            pass

    os.system('rm /root/pathfile')
except:
    logging.error('Some exceptions have shown up within this script, please stop and diagnose it!')

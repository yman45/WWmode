import time
import datetime
import threading
import logging
import ipaddress
from argparse import ArgumentParser
from queue import Queue
from ZODB import FileStorage, DB
from utils.load_settings import Settings
from utils.update_db import worker, Device
from utils.dbutils import DBOpen, db_check


logger = logging.getLogger('wwmode_app')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('logs/devdb.log')
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    '%d %B %Y %H:%M:%S.%03d')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(ch)

parser = ArgumentParser(allow_abbrev=False)
action = parser.add_mutually_exclusive_group(required=True)
action.add_argument('-U', '--update', dest='action', action='store_const',
                    const='update', help='start DB update procedure')
action.add_argument('-S', '--show', dest='action', action='store_const',
                    const='show', help='show information about devices')
action.add_argument('-F', '--find', dest='action', action='store_const',
                    const='find', help='search device cards in DB')
group_s = parser.add_argument_group('-S', 'show options')
group_s.add_argument('-a', '--all', dest='show_all', action='store_true',
                     help='show all devices in compressed fashion')
group_s.add_argument('-d', '--device', dest='show_dev', metavar='DEVICE',
                     help='show full device card chosen by FQDN or IP')
group_s.add_argument('-i', '--inactive', dest='inactive', action='store_true',
                     help='show devices that was not found by last update')
group_f = parser.add_argument_group('-F', 'find options')
group_f.add_argument('-v', '--find-vlan', dest='find_vlan', metavar='VLAN',
                     help='show all switches with VLAN configured')
group_f.add_argument('-f', '--full-search', dest='full_search',
                     metavar='SEARCH',
                     help='show compressed device cards where SEARCH was found')
group_f.add_argument('-o', '--older-software', dest='older_software',
                     metavar=('MODEL', 'VERSION'), nargs=2,
                     help='''show all switches of MODEL with older VERSION of
                     software''')
group_f.add_argument('-n', '--newer-software', dest='newer_software',
                     metavar=('MODEL', 'VERSION'), nargs=2,
                     help='''show all switches of MODEL with newer VERSION of
                     software''')
group_f.add_argument('-t', '--outdated', dest='outdated', action="store_true",
                     help='show devices with outdated software')
args = parser.parse_args()

run_set = Settings()
run_set.load_conf()


def update_cmd():
    '''Update device database using multithreading with utils/update_db.worker
    function. Update do not use DBOpen custom context manager because workers
    make connections themselves to only one instance of DB
    No args & return value
    '''
    start_time = time.time()
    q = Queue()
    threads = []
    num_threads = int(run_set.num_threads)
    total_hosts = [x for subnet in run_set.subnets for x in subnet.hosts()]
    total_hosts.extend(run_set.hosts)
    if num_threads > len(total_hosts):
        num_threads = len(total_hosts)
    db_check(run_set.db_name, run_set.db_tree)
    storage = FileStorage.FileStorage(run_set.db_name)
    db = DB(storage, pool_size=50)
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(q, run_set, db))
        t.start()
        threads.append(t)
    for item in total_hosts:
        q.put(item)
    q.join()
    for i in range(num_threads):
        q.put(None)
    for t in threads:
        t.join()
    db.close()
    logger.debug('Total execution time: {:.2f} sec.'.format(
        time.time() - start_time))
    logger.debug('New hosts founded: {}'.format(Device.num_instances))
    logger.debug('Total hosts founded: {}'.format(Device.founded_hosts))


def search_db(field, value):
    '''Search for given value through requested records attribute & print it
    Args:
        field - attribute in where we look for value
        value - value to find
    No return value
    '''
    def run_search(attr, val):
        with DBOpen(run_set.db_name) as connection:
            dbroot = connection.root()
            devdb = dbroot[run_set.db_tree]
            for dev in devdb:
                try:
                    dev_val = getattr(devdb[dev], attr)
                except AttributeError:
                    continue
                if val in dev_val and attr is not 'vlans':
                    print("{} - {} - {} >>> {}".format(
                        devdb[dev].ip, devdb[dev].dname, devdb[dev].location,
                        dev_val))
                elif val in dev_val:
                    print("{} - {} - {}".format(
                        devdb[dev].ip, devdb[dev].dname, devdb[dev].location))
    if field == 'full':
        for a in ['ip', 'dname', 'contact', 'location', 'model', 'firmware']:
            run_search(a, value)
    else:
        run_search(field, value)


def print_devices(device):
    '''Print device card in compressed fashion
    Args:
        device - device to print
    No return value
    '''
    try:
        print("{} - {} - {} - {}".format(
            device.ip, device.dname, device.location,
            device.model))
    except AttributeError:
        try:
            print("{} - {} - {}".format(
                device.ip, device.dname, device.location))
        except AttributeError:
            print("{} - {}".format(device.ip, device.location))


def show_cmd(device=None, inactive=False, inactivity_time=600):
    '''Print out all records in short or full record for host if it's domain
    name or IP address provided
    Args:
        device - device to be printed (DEFAULT - None)
        inactive - flag to show only inactive devices (not found by last update)
            (DEFAULT - False)
        inactivity_time - time interval between last transaction and
            device.last_seen to consider device inactive (DEFAULT - 600)
    No return value
    '''
    storage = FileStorage.FileStorage(run_set.db_name)
    last_transaction_time = datetime.datetime.fromtimestamp(
        storage.undoLog(0, 1)[0]['time'])
    del storage  # delete lock for DBOpen can work next
    with DBOpen(run_set.db_name) as connection:
        dbroot = connection.root()
        devdb = dbroot[run_set.db_tree]
        if device:
            try:
                ipaddress.ip_address(device)
                if device in devdb.keys():
                    print(devdb[device])
                else:
                    print("No device with that IP in DB")
            except ValueError:
                q_list = list(
                    [devdb[x] for x in devdb if devdb[x].dname == device])
                if q_list:
                    print(q_list[0])
                else:
                    print("No such domain name in DB")
            return
        for dev in devdb:
            if not inactive:
                print_devices(devdb[dev])
            elif inactive:
                dev_last_contacted = datetime.datetime.strptime(
                    devdb[dev].last_seen, '%d-%m-%Y %H:%M')
                diff = abs((
                    dev_last_contacted - last_transaction_time).total_seconds())
                if diff > inactivity_time:
                    print_devices(devdb[dev])
        if not inactive:
            print('Total stored devices - {}'.format(len(devdb.items())))


def software_search(model, version, older=True):
    '''Search for software older or newer then provided
    Args:
        model - devices of what model we search
        version - software version for comparison with
        older - do we search older or newer software (DEFAULT - True)
    No return value
    '''

    def check_soft(one, another):
        '''Helper function for search or greter or lesser
        Args:
            one - first comparison value
            other - second comparison value
        Return:
            True of False - result of comparison
        '''
        if older and another < one:
            return True
        elif not older and another > one:
            return True
        else:
            return False

    with DBOpen(run_set.db_name) as connection:
        dbroot = connection.root()
        devdb = dbroot[run_set.db_tree]
        for dev in devdb:
            try:
                devdb[dev].model
            except AttributeError:
                continue
            if model.upper() in devdb[dev].model and check_soft(
                    version, devdb[dev].firmware):
                print_devices(devdb[dev])


def find_newest_firmware():
    '''Find newest firmware in DB(!) for every device model in DB
    No args
    Return:
        model, version - model of device, latest firmware for that model
    '''
    with DBOpen(run_set.db_name) as connection:
        dbroot = connection.root()
        devdb = dbroot[run_set.db_tree]
        d = {}
        for dev in devdb:
            try:
                devdb[dev].model
            except AttributeError:
                continue
            if devdb[dev].model not in d or (
                    devdb[dev].firmware > d[devdb[dev].model]):
                d[devdb[dev].model] = devdb[dev].firmware
    print(d)
    for model in d:
        yield model, d[model]

if args.action == 'update':
    update_cmd()
elif args.action == 'show':
    if args.show_all:
        show_cmd(None)
    elif args.show_dev:
        show_cmd(args.show_dev)
    elif args.inactive:
        show_cmd(inactive=True)
elif args.action == 'find':
    if args.find_vlan:
        search_db('vlans', args.find_vlan)
    elif args.full_search:
        search_db('full', args.full_search)
    elif args.older_software:
        software_search(*args.older_software)
    elif args.newer_software:
        software_search(*args.newer_software, older=False)
    elif args.outdated:
        for model, version in find_newest_firmware():
            software_search(model, version)

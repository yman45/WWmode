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
action.add_argument('-G', '--generate', dest='action', action='store_const',
                    const='generate', help='generate usefull info from DB')
group_s = parser.add_argument_group('-S', 'show options')
group_s.add_argument('-a', '--all', dest='show_all', action='store_true',
                     help='show all devices in compressed fashion')
group_s.add_argument('-d', '--device', dest='show_dev', metavar='DEVICE',
                     help='show full device card chosen by FQDN or IP')
group_s.add_argument('-i', '--inactive', dest='inactive', action='store_true',
                     help='show devices that was not found by last update')
group_s.add_argument('-u', '--uplink-chain', dest='uplink_chain',
                     metavar='DEVICE', help='print device uplink chain')
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
group_f.add_argument('-t', '--outdated', dest='outdated', action='store_true',
                     help='show devices with outdated software')
group_g = parser.add_argument_group('-G', 'generate option')
group_g.add_argument('--tacacs', dest='tacacs', action='store_true',
                     help='generate list of hosts for tacacs')
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


def show_all_records(inactive=False, inactivity_time=600):
    '''Print out all DB records in compressed fashion.
    Args:
        inactive - if that flag in True state, print only inactive devices
            (not contacted in last update run (see next arg)) (DEFAULT - False)
        inactivity_time - consider device inactive if that time of seconds
            elapsed betwen update time and device last_seen (update time -
            time of last DB transaction, there can be some minutes between
            first device update and last transaction) (DEFAULT - 600)
    No return value
    '''
    if inactive:
        storage = FileStorage.FileStorage(run_set.db_name)
        last_transaction_time = datetime.datetime.fromtimestamp(
            storage.undoLog(0, 1)[0]['time'])
        del storage  # delete lock for DBOpen can work next
        counter = 0
    for num, dev in enumerate(device_generator()):
        if not inactive:
            print_devices(dev)
        else:
            dev_last_contacted = datetime.datetime.strptime(
                dev.last_seen, '%d-%m-%Y %H:%M')
            diff = abs((
                dev_last_contacted - last_transaction_time).total_seconds())
            if diff > inactivity_time:
                print_devices(dev)
                counter += 1
    count = counter if inactive else num
    print('Total showed devices - {}'.format(count))


def show_single_device(device, quiet=False):
    '''Print full device record and return device object. Device can be quried
    by IP address or domain name (FQDN or just main part, function add default
    domain and default prefix on it's own.
    Args:
        device - IP address or domain name
        quiet - don't print record
    Return:
        device object
    '''
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
                # there can be couple of items with 'device' in dname so we
                # make a list and choose first
                rec = ''
                mod = ''
                if len(device.split('.')) == 1:
                    mod = (run_set.domain_prefix + '.' + device + '.' +
                           run_set.default_zone)
                elif len(device.split('.')) == 2:
                    mod = device + '.' + run_set.default_zone
                elif run_set.default_zone and len(device.split('.')) == len(
                        run_set.default_zone.split('.')) + 1:
                    mod = run_set.domain_prefix + device
                q_list = list(
                    [devdb[x] for x in devdb if devdb[x].dname == device])
                m_list = list(
                    [devdb[x] for x in devdb if devdb[x].dname == mod])
                if q_list:
                    rec = q_list[0]
                elif m_list:
                    rec = m_list[0]
                if not quiet:
                    if rec:
                        print(rec)
                    else:
                        print("No such domain name in DB")
                return rec


def device_generator():
    '''Open ZODB, unpack device records and yields it one at a time.
    No args
    Return:
        devdb[dev] - device record from DB
    '''
    with DBOpen(run_set.db_name) as connection:
        dbroot = connection.root()
        devdb = dbroot[run_set.db_tree]
        for dev in devdb:
            yield devdb[dev]


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
    for dev in device_generator():
        try:
            dev.model
        except AttributeError:
            continue
        if model.upper() in dev.model and check_soft(
                version, dev.firmware):
            print_devices(dev)


def find_newest_firmware():
    '''Find newest firmware in DB(!) for every device model in DB
    No args
    Return:
        model, version - model of device, latest firmware for that model
    '''
    d = {}
    for dev in device_generator():
        try:
            dev.model
        except AttributeError:
            continue
        if dev.model not in d or (
                dev.firmware > d[dev.model]):
            d[dev.model] = dev.firmware
    print(d)
    for model in d:
        yield model, d[model]


def generate_tacacs_list():
    '''Generate list of allowed hosts for TACACS+ before.sh script
    No args & return values
    '''
    for dev in device_generator():
        if dev.dname.startswith(('n', 's', 'vc')):
            node_type = 'nodes'
        else:
            node_type = 'sites'
        print('{} {} {}'.format(node_type, dev.ip, dev.dname))


def go_high(device):
    '''Print device uplink chain from given device to upper level that can
    be find
    Args:
        device - IP address or domain name of device (FQDN or main part)
    No return value
    '''
    dev = show_single_device(device, quiet=True)
    if not dev:
        return
    print(dev.location)
    for up in dev.uplinks:
        go_high(up[0].split('@')[-1])
    else:
        print('-' * 10)


def show_cmd():
    '''Interlayer function for different show command execution
    based on provided CLI args
    '''
    if args.show_all:
        show_all_records()
    elif args.show_dev:
        show_single_device(args.show_dev)
    elif args.inactive:
        show_all_records(inactive=True)
    elif args.uplink_chain:
        go_high(args.uplink_chain)


def find_cmd():
    '''Interlayer function for different find command execution
    based on provided CLI args
    '''
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


def generate_cmd():
    '''Interlayer function for different generate command execution
    based on provided CLI args
    '''
    if args.tacacs:
        generate_tacacs_list()

action_dict = {
    'update': update_cmd,
    'show': show_cmd,
    'find': find_cmd,
    'generate': generate_cmd
}
action_dict[args.action]()

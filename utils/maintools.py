import datetime
import time
import threading
import ipaddress
import logging
import re
from queue import Queue
from ZODB import FileStorage, DB
from utils.load_settings import Settings
from utils.update_db import worker, Device
from utils.dbutils import db_check, DBOpen, get_last_transaction_time
from lexicon.translate import convert

m_logger = logging.getLogger('wwmode_app.utils.utils')
run_set = Settings()
run_set.load_conf()


def update_db_run():
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
    m_logger.debug('Total execution time: {:.2f} sec.'.format(
        time.time() - start_time))
    m_logger.debug('New hosts founded: {}'.format(Device.num_instances))
    m_logger.debug('Total hosts founded: {}'.format(Device.founded_hosts))


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


def compute_time_diff(one, another):
    if isinstance(another, Device):
            another = datetime.datetime.strptime(
                another.last_seen, '%d-%m-%Y %H:%M')
    return abs((one - another).total_seconds())


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
        last_transaction_time = get_last_transaction_time(run_set.db_name)
        counter = 1
    for num, dev in enumerate(device_generator()):
        if not inactive:
            print_devices(dev)
        else:
            diff = compute_time_diff(last_transaction_time, dev)
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
        quiet - don't print record (DEFAULT - False)
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
    for k, v in d.items():
        print('{}: {}'.format(k, v))
    print('-' * 30)
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


def generate_dns_list():
    '''Generate list of DNS records based on SNMP location
    Output of that function can be very weird and most likely
    need manual intervention!
    No args & return values
    '''
    for dev in device_generator():
        if not dev.location:
            continue
        dev_loc = convert(dev.location, schema=run_set.location).lower()
        if ',' in dev_loc:
            if re.search(r'\d{0,4}(-.{1,3} )?(\D )*?\d{1,3}',
                         dev_loc.split(',')[0]):
                dev_loc = dev_loc.split(',')[0]
            else:
                print('{}\t\t\tIN A\t\t\t{}'.format(dev_loc.split(',')[0],
                                                    dev.ip))
                continue
        print('{}\t\t\tIN A\t\t\t{}'.format(generate_dname(dev_loc, 'p', '1'),
                                            dev.ip))


def generate_dname(address, role, number):
    '''Generate domain name from postal address using custom Intertax rules
    Args:
        address - postal address
        role - device role (one letter: p, n, s...
        number - device ordinal number
    Return:
        generated domain name (without zone)
    '''
    vowels = ('a', 'e', 'i', 'o', 'u', 'y')
    address = re.sub(r'[^a-zA-Z0-9 .,]', '', address).lower()
    if ',' in address:
        address = address.split(',')[0]
    location_pattern = re.compile(
        r'^(?P<fnum>\d{0,4})(?:-.{1,3} )?(?P<street>.+?) (?P<lnum>\d{1,3}.*)$')
    location_match = location_pattern.match(address)
    if not location_match:
        return role + number + '.' + address.replace(' ', '')
    middle_part = location_match.group('street')
    if len(middle_part.split()) > 1:
        middle_part_split = middle_part.split()
        middle_part_last_word = middle_part_split.pop(-1)
        middle_part = ''
        for word in middle_part_split:
            middle_part += word[0]
        middle_part += middle_part_last_word
    tmp_word = ''
    for num, letter in enumerate(middle_part):
        if num > 3 and letter not in vowels:
            break
        elif num > 3 and middle_part[num-1] not in vowels:
            break
        tmp_word += letter
    if middle_part[num-1] in vowels:
        tmp_word += middle_part[num]
    last_part = ''
    for part in location_match.group('lnum').split():
        if part[0].isdigit():
            last_part += part
        else:
            last_part += part[0]
    dname = ''
    for part in [location_match.group('fnum'), tmp_word, last_part]:
        if part:
            dname += part
    return role + number + '.' + dname


def go_high(device):
    '''Print device uplink chain from given device to upper level that can
    be find
    Args:
        device - IP address or domain name of device (FQDN or main part)
    No return value
    '''
    dev = show_single_device(device, quiet=True)
    if not dev:
        print('-'*10)
        return
    print(dev.location)
    for up in dev.uplinks:
        go_high(up[0].split('@')[-1])

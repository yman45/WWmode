import datetime
import time
import threading
import ipaddress
import logging
import re
import os
import os.path
import smtplib
from email.mime.text import MIMEText
from queue import Queue
from ZODB import FileStorage, DB
import transaction
from utils.load_settings import AppSettings, FakeSettings
from utils.update_db import worker, Device
from utils.dbutils import db_check, DBOpen, get_last_transaction_time
from lexicon.translate import convert

m_logger = logging.getLogger('wwmode_app.utils.utils')
run_set = AppSettings()
run_set.load_conf()
if not os.path.isdir(run_set.logs_path):
    os.mkdir(run_set.logs_path)


def update_db_run():
    '''Update device database using multithreading with utils/update_db.worker
    function. Update do not use DBOpen custom context manager because workers
    make connections themselves to only one instance of DB
    No args & return value
    '''
    start_time = time.time()
    try:
        num_threads = int(run_set.num_threads)
    except ValueError:
        m_logger.error('Incorrect number of threads - {}'.format(num_threads))
        num_threads = 10
    db_check(run_set.db_name, run_set.db_tree)
    storage = FileStorage.FileStorage(run_set.db_name)
    db = DB(storage, pool_size=num_threads)
    for group in run_set.groups.values():
        q = Queue()
        threads = []
        total_hosts = [x for subnet in group.subnets for x in subnet.hosts()]
        total_hosts.extend(group.hosts)
        if num_threads > len(total_hosts):
            num_threads = len(total_hosts)
        settings = FakeSettings(run_set, group)
        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(q, settings, db))
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
    exec_time_msg = 'Total execution time: {:.2f} sec.'.format(
        time.time() - start_time)
    new_hosts_msg = 'New hosts founded: {}'.format(Device.num_instances)
    total_hosts_msg = 'Total hosts founded: {}'.format(Device.founded_hosts)
    m_logger.debug(exec_time_msg)
    m_logger.debug(new_hosts_msg)
    m_logger.debug(total_hosts_msg)
    if Device.new_hosts and run_set.mail_to:
        print(Device.new_hosts)
        r_list = generate_rancid_list(Device.new_hosts)
        p_list = generate_plain_list(Device.new_hosts)
        d_list = generate_dns_list(Device.new_hosts)
        t_list = generate_trac_table(Device.new_hosts)
        n_list = generate_nagios_list(Device.new_hosts)
        cfg_msg = 'Config for new devices:\n'
        raw_msg = 'Run complete.\n' + exec_time_msg + '\n' + new_hosts_msg
        raw_msg += '\n' + total_hosts_msg + '\n' + cfg_msg + '\n' + r_list
        raw_msg += '\n' + p_list + '\n' + d_list + '\n' + t_list + '\n'
        raw_msg += n_list + '\n'
        msg = MIMEText(raw_msg.encode('utf-8'), _charset='utf-8')
        msg['Subject'] = run_set.mail_subject
        msg['From'] = run_set.mail_from
        msg['To'] = run_set.mail_to
        try:
            smtp = smtplib.SMTP(host=run_set.mail_serv)
            smtp.send_message(msg)
            smtp.quit()
        except smtplib.SMTPException as e:
            m_logger.error("Email sending failed with error: {}".format(e))


def search_db(field, value):
    '''Search for given value through requested records attribute & print it
    Args:
        field - attribute in where we look for value
        value - value to find
    No return value
    '''
    def run_search(attr, val):
        '''Supporting function for value searching in specific field
        args:
            attr - field to look in
            val - value to find
        No return value
        '''
        with DBOpen(run_set.db_name) as connection:
            dbroot = connection.root()
            devdb = dbroot[run_set.db_tree]
            for dev in devdb:
                try:
                    dev_val = getattr(devdb[dev], attr)
                except AttributeError:
                    continue
                if val in dev_val and attr is not 'c_vlans':
                    print("{} - {} - {} >>> {}".format(
                        devdb[dev].ip, devdb[dev].dname, devdb[dev].c_location,
                        dev_val))
                elif val in dev_val:
                    print("{} - {} - {}".format(
                        devdb[dev].ip, devdb[dev].dname,
                        devdb[dev].c_location))
    if field == 'full':
        for a in ['ip', 'dname', 'c_contact', 'c_location', 'c_model',
                  'c_firmware']:
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
            device.ip, device.dname, device.c_location, device.c_model))
    except AttributeError:
        print("{} - {} - {}".format(
              device.ip, device.c_location, device.c_model))


def compute_time_diff(one, another):
    '''Compute time differences between one time and another one. If another
    one is a Device instance, then grub it last seen time.
    args:
        one - first time
        another - second time OR Device instance
    Return:
        absolute difference in seconds
    '''
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
                if device in devdb:
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
                    mod = run_set.domain_prefix + '.' + device
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


def device_generator(hosts=None):
    '''Open ZODB, unpack device records and yields it one at a time.
    Args:
        hosts - list of hosts to be yielded (default - None, so yield all
            of them)
    Return:
        devdb[dev] - device record from DB
    '''
    with DBOpen(run_set.db_name) as connection:
        dbroot = connection.root()
        devdb = dbroot[run_set.db_tree]
        if hosts:
            yield from [devdb[x] for x in hosts if x in devdb]
        else:
            yield from [devdb[x] for x in devdb]


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
            dev.c_model
        except AttributeError:
            continue
        if model.upper() in dev.c_model and check_soft(
                version, dev.c_firmware):
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
            dev.c_firmware
        except AttributeError:
            continue
        if dev.c_model not in d or (
                dev.c_firmware > d[dev.c_model]):
            d[dev.c_model] = dev.c_firmware
    for k, v in d.items():
        print('{}: {}'.format(k, v))
    print('-' * 30)
    for model in d:
        yield model, d[model]


def generate_plain_list(hosts=None):
    '''Generate list of hosts domain names one on a line
    Args:
        hosts - list of hosts which values need to be generated
    Return:
        overall - string containing all resulting list
    '''
    overall = 'Plain list entries:\n'
    for dev in device_generator(hosts):
        if dev.dname:
            result = '{}'.format(dev.dname)
            if not hosts:
                print(result)
            overall += result + '\n'
    return overall


def generate_dns_list(hosts=None):
    '''Generate list of DNS records based on SNMP location
    Output of that function can be very weird and most likely
    need manual intervention!
    Args:
        hosts - list of hosts which values need to be generated
    Return:
        overall - string containing all resulting list
    '''
    overall = 'DNS list entries:\n'
    for dev in device_generator(hosts):
        if not dev.c_location:
            continue
        dev_loc = convert(dev.c_location,
                          schema=run_set.location_transliteration).lower()
        if ',' in dev_loc:
            if re.search(r'\d{0,4}(-.{1,3} )?(\D )*?\d{1,3}',
                         dev_loc.split(',')[0]):
                dev_loc = dev_loc.split(',')[0]
            else:
                print('{}\t\t\tIN A\t\t\t{}'.format(dev_loc.split(',')[0],
                                                    dev.ip))
                continue
        result = '{}\t\t\tIN A\t\t\t{}'.format(generate_dname(dev_loc, 'p',
                                                              '1'), dev.ip)
        if not hosts:
            print(result)
        overall += result + '\n'
    return overall


def generate_nagios_list(hosts=None):
    '''Generate Nagios host definitions
    Args:
        hosts - list of hosts which values need to be generated
    Return:
        overall - string containing all resulting list
    '''
    overall = 'Nagios list entries:\n'
    for dev in device_generator(hosts):
        if not dev.dname:
            continue
        template = 'define host{\n'
        template += '\tuse\t\tgeneric-host\n\thostname\t{}\n'.format(
            dev.dname)
        if hasattr(dev, 'c_location') and dev.c_location:
            template += '\talias\t\tDEVICE at {}\n'.format(dev.c_location)
        template += '\taddress\t\t{}\n'.format(dev.ip)
        if hasattr(dev, 'c_uplinks'):
            template += '\tparents\t\t'
            for node in dev.c_uplinks:
                if node:
                    template += node[0] + ','
            template = template[:-1]
            template += '\n'
        template += '}\n'
        if not hosts:
            print(template)
        overall += template + '\n'
    return overall


def generate_rancid_list(hosts=None):
    '''Generate Rancid router.db list
    Args:
        hosts - list of hosts which values need to be generated
    Return:
        overall - string containing all resulting list
    '''
    overall = 'Rancid router.db entries:\n'
    for dev in device_generator(hosts):
        if not dev.dname:
            continue
        if hasattr(dev, 'rancid_type'):
            result = '{};{};up'.format(dev.dname, dev.rancid_type)
            if not hosts:
                print(result)
            overall += result + '\n'
    return overall


def generate_trac_table(hosts=None):
    '''Generate markdown table for Trac knowledge base
    Args:
        hosts - list of hosts which values need to be generated
    Return:
        overall - string containing all resulting list
    '''
    if not hosts:
        header = '|| Location || Device model || Domain name || IP address ||'
        header += ' Link speed ||'
        print(header)
    overall = 'Trac table entries:\n'
    for dev in device_generator(hosts):
        template = '|| '
        t_location = getattr(dev, 'c_location', '  ')
        t_model = getattr(dev, 'c_model', '  ')
        t_dname = getattr(dev, 'dname', '  ')
        template += t_location + ' || ' + t_model + ' || ' + t_dname + ' || '
        template += dev.ip + ' || '
        if hasattr(dev, 'c_uplinks') and dev.c_uplinks:
            template += dev.c_uplinks[0][1] + ' ||'
        else:
            template += '  ||'
        if not hosts:
            print(template)
        overall += template + '\n'
    return overall


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
    if not hasattr(run_set, 'uplink_pattern'):
        print('no uplink pattern defined')
        return
    pattern = re.compile(run_set.uplink_pattern)
    dev = show_single_device(device, quiet=True)
    if not dev:
        print('-'*10)
        return
    print(dev.c_location)
    for up in dev.c_uplinks:
        m_res = pattern.match(up[0])
        if m_res:
            try:
                up_dev = m_res.group('device')
            except IndexError:
                up_dev = up[0]
        go_high(up_dev)


def dry_run():
    '''Print out config
    No args & return value
    '''
    for arg in dir(run_set):
        if arg.startswith('__') and arg.endswith('__'):
            continue
        print('{}:\t{}'.format(arg, getattr(run_set, arg)))


def delete_record(ip):
    '''Delete record frow DB
    Args:
        ip - IP address of device to be deleted
    No return value
    '''
    with DBOpen(run_set.db_name) as connection:
        dbroot = connection.root()
        devdb = dbroot[run_set.db_tree]
        del devdb[ip]
        transaction.commit()
    print('Deletion done!')

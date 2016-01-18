import time
import threading
import logging
import ipaddress
from optparse import OptionParser
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

usage = "usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-u", "--update", dest="update", action="store_true",
                  help="update DB by sending queries to devices")
parser.add_option("-s", "--show-all", dest="show_all", action="store_true",
                  help="show all devices")
parser.add_option("-d", "--show", dest="show_dev",
                  help="show device card")
parser.add_option("-v", "--find-vlan", dest="find_vlan",
                  help="show all switches with VLAN configured")
parser.add_option("-f", "--full-search", dest="full_search",
                  help="show records with match in any field")
(options, args) = parser.parse_args()

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


def show_cmd(device=None):
    '''Print out all records in short or full record for host if it's domain
    name or IP address provided
    Args:
        device - device to be printed (DEFAULT - None)
    No return value
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
                q_list = list(
                    [devdb[x] for x in devdb if devdb[x].dname == device])
                if q_list:
                    print(q_list[0])
                else:
                    print("No such domain name in DB")
            return
        for dev in devdb:
            try:
                print("{} - {} - {} - {}".format(
                    devdb[dev].ip, devdb[dev].dname, devdb[dev].location,
                    devdb[dev].model))
            except AttributeError:
                try:
                    print("{} - {} - {}".format(
                        devdb[dev].ip, devdb[dev].dname, devdb[dev].location))
                except AttributeError:
                    print("{} - {}".format(devdb[dev].ip, devdb[dev].location))
        print('Total stored devices - {}'.format(len(devdb.items())))

if options.update:
    update_cmd()
elif options.show_all:
    show_cmd(None)
elif options.show_dev:
    show_cmd(options.show_dev)
elif options.find_vlan:
    search_db('vlans', options.find_vlan)
elif options.full_search:
    search_db('full', options.full_search)

import time
import threading
import logging
import sys
import ipaddress
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
    with DBOpen(run_set.db_name) as connection:
        dbroot = connection.root()
        devdb = dbroot[run_set.db_tree]
        for dev in devdb:
            try:
                dev_val = getattr(devdb[dev], field)
            except AttributeError:
                continue
            if not isinstance(dev_val, list) and dev_val == value:
                print("{} - {} - {}".format(devdb[dev].ip, devdb[dev].dname,
                                            devdb[dev].location))
            elif isinstance(dev_val, list) and value in dev_val:
                print("{} - {} - {}".format(devdb[dev].ip, devdb[dev].dname,
                                            devdb[dev].location))


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

HELP_MSG = """
WWmode is a tool for collecting data about devices in network, store it in
database and search through it.
    -update :for update database, it automatically check hosts for some errors
    -search -attr value :search in db for match of value in attr of records
        -search vlans 505
    -show: to short output for each record in base
    -show value: for full output of one record (value for IP or FQDN)
"""
if len(sys.argv) < 2:
    print(HELP_MSG)
    exit(1)
elif sys.argv[1] == '-update' and len(sys.argv) > 2:
    print("Update command doesn't allow options.")
    exit(1)
elif sys.argv[1] == '-update':
    update_cmd()
elif sys.argv[1] == '-show':
    if len(sys.argv) == 3:
        pr_device = sys.argv[2]
    elif len(sys.argv) > 3:
        print("Too many options for show command")
        exit(1)
    else:
        pr_device = None
    show_cmd(pr_device)
elif sys.argv[1] == '-search':
    search_db(sys.argv[2][1:], sys.argv[3])
else:
    print(HELP_MSG)
    exit(1)

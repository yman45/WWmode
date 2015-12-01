import time
import threading
import logging
import sys
from queue import Queue
from ZODB import FileStorage, DB
import transaction
from utils.load_settings import Settings
from utils.update_db import worker, Device


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


def db_check(db, treename):
    '''Create database tree if it doesn't exist
    Args:
        db - instance of ZODB.DB class
        treename - name of tree
    No return value
    '''
    connection = db.open()
    dbroot = connection.root()
    if treename not in dbroot:
        logger.info('Create new devdb')
        from BTrees.OOBTree import OOBTree
        dbroot[treename] = OOBTree()
        transaction.commit()
    connection.close()


def update_cmd():
    '''Update device database using multithreading with utils/update_db.worker
    function
    No args & return value
    '''
    start_time = time.time()
    q = Queue()
    threads = []
    run_set = Settings()
    run_set.load_conf()
    run_set.num_threads = int(run_set.num_threads)
    total_hosts = [x for subnet in run_set.subnets for x in subnet.hosts()]
    if run_set.num_threads > len(total_hosts):
        run_set.num_threads = len(total_hosts)
    storage = FileStorage.FileStorage(run_set.db_name)
    db = DB(storage)
    db_check(db, run_set.db_tree)
    for i in range(run_set.num_threads):
        t = threading.Thread(target=worker, args=(q, run_set, db))
        t.start()
        threads.append(t)

    for item in total_hosts:
        q.put(item)
    q.join()

    for i in range(run_set.num_threads):
        q.put(None)
    for t in threads:
        t.join()
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
    run_set = Settings()
    run_set.load_conf()
    storage = FileStorage.FileStorage(run_set.db_name)
    db = DB(storage)
    connection = db.open()
    dbroot = connection.root()
    devdb = dbroot[run_set.db_tree]
    for dev in devdb:
        if field != 'vlans' and getattr(devdb[dev], field) == value:
            print("{} - {} - {}".format(devdb[dev].ip, devdb[dev].dname,
                                        devdb[dev].location))
        elif field == 'vlans' and value in getattr(devdb[dev], field):
            print("{} - {} - {}".format(devdb[dev].ip, devdb[dev].dname,
                                        devdb[dev].location))

HELP_MSG = """
WWmode is a tool for collecting data about devices in network, store it in
database and search through it.
    -update :for update database, it automatically check hosts for some errors
    -search -attr value :search in db for match of value in attr of records
        -search vlans 505
"""
if len(sys.argv) < 2:
    print(HELP_MSG)
    exit(1)
elif sys.argv[1] == '-update' and len(sys.argv) > 2:
    print("Update command doesn't allow options.")
    exit(1)
elif sys.argv[1] == '-update':
    update_cmd()
elif sys.argv[1] == '-search':
    search_db(sys.argv[2][1:], sys.argv[3])
else:
    print(HELP_MSG)
    exit(1)

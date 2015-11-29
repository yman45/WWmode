import time
import threading
import logging
from queue import Queue
from ZODB import FileStorage, DB
import transaction
from utils.load_settings import Settings
from utils.update_db import worker, Device


def db_check(db, treename):
    connection = db.open()
    dbroot = connection.root()
    if treename not in dbroot:
        logger.info('Create new devdb')
        from BTrees.OOBTree import OOBTree
        dbroot[treename] = OOBTree()
        transaction.commit()
    connection.close()

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
start_time = time.time()
q = Queue()
threads = []
run_set = Settings()
run_set.load_conf()
run_set.num_threads = int(run_set.num_threads)
total_hosts = [x for subnet in run_set.subnets for x in subnet.hosts()]
if run_set.num_threads > len(total_hosts):
    run_set.num_threads = len(total_hosts)
storage = FileStorage.FileStorage('devdb.fs')
db = DB(storage)
db_check(db, 'devicedb')
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
print('Total execution time: {:.2f} sec.'.format(time.time() - start_time))
print('New hosts founded: {}'.format(Device.num_instances))
print('Total hosts founded: {}'.format(Device.founded_hosts))

import logging
import datetime
import transaction
from ZODB import FileStorage, DB

m_logger = logging.getLogger('wwmode_app.utils.dbutils')


class DBOpen:
    '''Context manager for open and close ZODB database
    instance attrs:
        db_name - name of file which contains db
        connection - connection to db
    methods:
        overloaded __init__
        overloaded __enter__
        overloaded __exit__
    '''
    def __init__(self, db_name):
        '''Add db name to instance
        Args:
            db_name - name of file which contains db
        Overloaded
        '''
        self.db_name = db_name

    def __enter__(self):
        '''Open connection to db
        No args
        Return:
            connection to db
        '''
        self.storage = FileStorage.FileStorage(self.db_name)
        self.db = DB(self.storage)
        self.connection = self.db.open()
        return self.connection

    def __exit__(self, exc_type, exc_value, exc_tb):
        '''Close connection to db and propogate exception if any with
        return False value
        Args:
            exc_type - type of exception
            exc_value - value of exception
            exc_tb - traceback of exception
        Return:
            False if there is an error
            Or None
        '''
        self.connection.close()
        self.db.close()
        if exc_type is not None:
            m_logger.error('DB: Got an exception {} with value {}.'.format(
                exc_type, exc_value))
            return False


def db_check(db_name, db_tree):
    '''Create database tree if it doesn't exist. Get tree name and db from
    loaded configuration file
    No args and return value
    '''
    with DBOpen(db_name) as connection:
        dbroot = connection.root()
        if db_tree not in dbroot:
            m_logger.info('Create new devdb')
            from BTrees.OOBTree import OOBTree
            dbroot[db_tree] = OOBTree()
            transaction.commit()


def get_last_transaction_time(db):
    '''Get time of last DB transaction
    Args:
        db - name of DB
    Return:
        time of last transaction
    '''
    storage = FileStorage.FileStorage(db)
    last_transaction_time = datetime.datetime.fromtimestamp(
        storage.undoLog(0, 1)[0]['time'])
    del storage  # delete DB lock
    return last_transaction_time

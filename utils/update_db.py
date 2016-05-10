import re
import socket
import logging
import datetime
from pysnmp.hlapi import SnmpEngine
import transaction
from persistent import Persistent
from utils.snmpget import SnmpGetter
from utils.load_cards import retrive
from lexicon.translate import convert
from utils.wwmode_exception import WWModeException


# Retrive all cards once when module imported
device_cards = retrive()

m_logger = logging.getLogger('wwmode_app.utils.update_db')


class SupplyZoneNameError(WWModeException):
    '''Exception to be raised if there are errors in default_zone setting'''
    pass


class NoNameInSupplyZone(WWModeException):
    '''Exception to be raised if there is no name domain name in supply zone'''
    pass


class Device(Persistent):
    '''Device representation class
    attrs:
        num_instances - all created instances (represent new hosts)
        founded_hosts - all hosts that found on the run
        ip - IPv4 address of device
        first_seen - datetime when instance created
    methods:
        overloaded __init__
        overloaded __str__
        test_domain_name
        translit_location
        check_supply_zone
        _p_resolveConflict (can be not working at all)
    '''
    num_instances = 0
    founded_hosts = 0

    def __init__(self, ip):
        '''Initialize vlans and uplinks lists and add 1 to class
        num_instances counters
        Args:
            ip - string representation of device IPv4 address
        Overloaded
        '''
        self.ip = ip
        self.first_seen = datetime.datetime.now().strftime('%d-%m-%Y %H:%M')
        Device.num_instances += 1
        m_logger.info('{}: New device: new device found'.format(self.ip))

    def __str__(self):
        '''Print out device record. Domain name concatenated first because
        it can be in record, while other info not
        No args
        Return:
            string representation of object
        Overloaded
        '''
        aligner = ' ' * 5
        prstr = ('{0}IPv4 address: {1}\n{0}First seen: {2}\n' +
                 '{0}Last seen: {3}\n{0}Device location: {4}\n' +
                 '{0}Device contact: {5}\n').format(
            aligner, self.ip, self.first_seen, self.last_seen, self.location,
            self.contact)
        try:
            dnamestr = "{}Domain name: {}\n".format(aligner, self.dname)
        except AttributeError:
            dnamestr = ""
        try:
            addstr = ('{0}Device model: {1}\n{0}Firmware version: {2}\n' +
                      '{0}VLAN list: {3}\n{0}Uplinks: {4}').format(
                          aligner, self.model, self.firmware, self.vlans,
                          self.uplinks)
        except AttributeError:
            addstr = ""
        return prstr + dnamestr + addstr

    def _p_resolveConflict(self, old_state, saved_state, new_state):
        '''Method for DB conflicts to be resolved. As we do not trying to
        write devices by many threads it just save new_state, resolving
        odd conflicts only
        Args:
            old_state - value that transaction based on when start
            saved_state - value that transaction really found in DB
            new_state - value that transaction want to write
        Return:
            new_state
        '''
        m_logger.warning('''{}: DB conflict: got a conflict, new - {}, old - {}
                         , saved - {}'''.format(self.ip, new_state, old_state,
                                                saved_state))
        return new_state

    def test_domain_name(self):
        '''Get device FQDN from PTR & test that A record of PTR value point
        to same IP address, log error if not
        No args & return value
        '''
        try:
            self.dname, alias, addresslist = socket.gethostbyaddr(self.ip)
            try:
                return_ip = socket.gethostbyname(self.dname)
                if self.ip != return_ip:
                    m_logger.error('{}: DNS: A record not same as PTR'.format(
                        self.ip))
            except socket.gaierror:
                m_logger.error('{}: DNS: No A record on received PTR'.format(
                    self.ip))
        except socket.herror:
            m_logger.error('{}: DNS: No PTR record for that host'.format(
                self.ip))
            self.dname = ''

    def check_supply_zone(self, zone, splitdots):
        '''Check for presence of domain name same as device name in supply_zone
        Args:
            zone - supply zone name, e.g. 'mon.local'
            splitdots - how many domain levels to split from device domain name
        Return:
            False if there is no domain name for device
            True if domain name presented in supply zone
            Can raise SupplyZoneError or NoNameInSupplyZone
        '''
        if not self.dname:
            return False
        try:
            name = '.'.join(self.dname.split('.')[:-splitdots])
        except IndexError:
            return SupplyZoneNameError
        try:
            socket.gethostbyname(name + '.' + zone)
        except:
            raise NoNameInSupplyZone
        else:
            return True

    def translit_location(self, schema):
        '''Translit device location using chosen schema
        Args:
            schema - file name where transliteration schema kept
        No return value
        '''
        if not self.location:
            pass
        try:
            self.location = convert(self.location, conv_from='lat',
                                    schema=schema)
        except OSError:
            pass


def worker(queue, settings, db):
    '''Update database by send request on all suplied hosts. Function designed
    for multithreaded use, so it get hosts from Queue. If host answer on
    sysDescr query, function try to recognize model and update or create new
    record on device in database
    Args:
        queue - instance of queue.Queue class which hold all hosts gathered
            from settings
        settings - instance of utils.load_settings.Settings
        db - instance of ZODB.DB class
    No return value
    Note: PySNMP compile SNMPv2-MIB::sysLocation & sysContact into OID
    without last 0. Second strange thing index=0 doesn't work at all. So I
    use numerical OID to retrive location and contact.
    '''
    location_oid = '1.3.6.1.2.1.1.6.0'
    contact_oid = '1.3.6.1.2.1.1.4.0'
    engine = SnmpEngine()
    connection = db.open()
    dbroot = connection.root()
    devdb = dbroot['devicedb']
    while True:
        dev_card = None
        host = queue.get()
        if host is None:
            transaction.commit()
            connection.close()
            break
        snmp_getter = SnmpGetter(engine, settings)
        sys_descr = snmp_getter.sget_sys_description(host.exploded)
        if not sys_descr:
            queue.task_done()
            continue
        if host.exploded not in devdb:
            devdb[host.exploded] = Device(host.exploded)
        device = devdb[host.exploded]
        Device.founded_hosts += 1
        device.last_seen = datetime.datetime.now().strftime('%d-%m-%Y %H:%M')
        snmp_getter.sget_equal(device, 'location', location_oid)
        snmp_getter.sget_equal(device, 'contact', contact_oid)
        if settings.location_transliteration != 'straight':
            device.translit_location(settings.location_transliteration)
        device.test_domain_name()
        if settings.supply_zone:
            try:
                device.check_supply_zone(settings.supply_zone,
                                         len(settings.default_zone.split('.')))
            except SupplyZoneNameError:
                m_logger.error(
                    'DNS: Incorrect parameters for supply zone check')
            except NoNameInSupplyZone:
                m_logger.error('{}: DNS: no domain name in {} zone'.format(
                    device.ip, settings.supply_zone))
        for card in device_cards:
            if re.search(card['info_pattern'], sys_descr):
                dev_card = card
                break
        if dev_card:
            device.vtree = True if 'vlan_tree_by_oid' in card else False
            wanted_params = settings.group_wanted
            wanted_params.update(settings.wanted_params)
            for param in wanted_params.keys():
                if param == 'uplinks':
                    oid = 'well-known'
                elif param + '_oid' not in dev_card.keys():
                    m_logger.warning('No OID for {}'.format(param))
                    continue
                else:
                    oid = dev_card[param + '_oid']
                getattr(snmp_getter, 'sget_' + wanted_params[param])(
                    device, param, oid)
            m_logger.info('{} ----> {}'.format(host, device.model))
        else:
            device.model = 'unrecognized'
            m_logger.info('{} unrecognized...'.format(host))
        queue.task_done()

import re
import socket
import logging
import datetime
from pysnmp.hlapi import SnmpEngine
import transaction
from persistent import Persistent
from utils.snmpget import snmp_run, process_output, get_with_send, tree_walk
from utils.load_cards import retrive
from lexicon.translate import convert
from utils.wwmode_exception import WWModeException


# Retrive all cards once when module imported
device_cards = retrive()

dtnow = datetime.datetime.now()
logfile = 'logs/update_db_' + dtnow.strftime('%d-%m-%Y_%H-%M') + '.log'
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s : %(message)s',
                    datefmt='%d %B %Y %H:%M:%S',
                    filename=logfile,
                    filemode='w')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)


class SupplyZoneNameError(WWModeException):
    '''Exception to be raised if there are errors in default_zone setting'''
    pass


class NoNameInSupplyZone(WWModeException):
    '''Exception to be raised if there is no name domain name in supply zone'''
    pass


class Device(Persistent):
    '''Device representation class

    class attrs:
        num_instances - all created instances (represent new hosts)
        founded_hosts - all hosts that found on the run
    instance attrs:
        ip - IPv4 address of device
        first_seen - datetime when instance created
        last_seen - datetime of last run when device seen
        dname - FQDN of device
        contact - SNMPv2-MIB::sysContact value
        location - SNMPv2-MIB::sysLocation value
        model - device model
        firmware - device firmware version
        vlans - list of VLANs configured on device
        uplinks - list of tuples(interface description, interface speed)
            recognized as uplink
        vlan_oid - OID by which VLANs can be found
        firmware_oid - OID by which firmware version can be found
        vtree - bool value that points on fact that VLAN number is in OID,
            not in received value
    methods:
        overloaded __init__
        overloaded __str__
        identify
        test_domain_name
        translit_location
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
        self.vlans = []
        self.uplinks = []
        Device.num_instances += 1
        logging.info('{}: New device: new device found'.format(self.ip))

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
        logging.warning('''{}: DB conflict: got a conflict, new - {}, old - {},
                        saved - {}'''.format(self.ip, new_state, old_state,
                                             saved_state))
        return new_state

    def identify(self, descr):
        '''Match sysDescr to device_cards to identify device model line
        Args:
            descr - SNMPv2::sysDescr value
        Return:
            card['model_oid'] - OID by witch device model can be found
        '''
        for card in device_cards:
            if re.search(card['info_pattern'], descr):
                self.vlan_oid = card['vlan_tree']
                self.vtree = True if 'vlan_tree_by_oid' in card else False
                self.firmware_oid = card['firmware_oid']
                return card['model_oid']

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
                    logging.error('{}: DNS: A record not same as PTR'.format(
                        self.ip))
            except socket.gaierror:
                logging.error('{}: DNS: No A record on received PTR'.format(
                    self.ip))
        except socket.herror:
            logging.error('{}: DNS: No PTR record for that host'.format(
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
        if not self.location.startswith('!') and ',' in self.location:
            delimeter = self.location.index(',')
        else:
            delimeter = 0
        try:
            self.location = convert(self.location, conv_from='lat',
                                    end=delimeter, schema=schema)
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
    engine = SnmpEngine()
    connection = db.open()
    dbroot = connection.root()
    devdb = dbroot['devicedb']
    while True:
        all_vlans = []
        all_uplinks = []
        host = queue.get()
        if host is None:
            transaction.commit()
            connection.close()
            break
        snmp_get = snmp_run(engine, settings.ro_community, host.exploded,
                            'sysDescr', mib='SNMPv2-MIB')
        error_indication, error_status, error_index, var_binds = next(snmp_get)
        oid, value = process_output(error_indication, error_status, error_index,
                                    var_binds, host.exploded)
        if not value:
            queue.task_done()
            continue
        if host.exploded not in devdb:
            devdb[host.exploded] = Device(host.exploded)
        device = devdb[host.exploded]
        Device.founded_hosts += 1
        device.last_seen = datetime.datetime.now().strftime('%d-%m-%Y %H:%M')
        oid, device.location = get_with_send(
            '1.3.6.1.2.1.1.6.0', host.exploded, snmp_get)
        if settings.location != 'straight':
            device.translit_location(settings.location)
        oid, device.contact = get_with_send(
            '1.3.6.1.2.1.1.4.0', host.exploded, snmp_get)
        device.test_domain_name()
        if not device.location.startswith('!'):
            try:
                device.check_supply_zone(settings.supply_zone,
                                         len(settings.default_zone.split('.')))
            except SupplyZoneNameError:
                logging.error('DNS: Incorrect parameters for supply zone check')
            except NoNameInSupplyZone:
                logging.error('{}: DNS: no domain name in {} zone'.format(
                    device.ip, settings.supply_zone))
        model_oid = device.identify(value)
        if model_oid:
            oid, device.model = get_with_send(model_oid, host.exploded,
                                              snmp_get)
            oid, device.firmware = get_with_send(device.firmware_oid,
                                                 host.exploded, snmp_get)
            for oid, vlan in tree_walk(engine, settings.ro_community,
                                       host.exploded, device.vlan_oid):
                if device.vtree:
                    vlan = oid.split('.')[-1]
                if vlan not in settings.unneded_vlans:
                    all_vlans.append(vlan)
            device.vlans = all_vlans
            for oid, if_descr in tree_walk(engine, settings.ro_community,
                                           host.exploded, 'ifAlias',
                                           mib='IF-MIB'):
                if if_descr and re.match(settings.uplink_pattern, if_descr):
                    if_index = oid.split('.')[-1]
                    oid, if_speed = get_with_send('ifHighSpeed', host.exploded,
                                                  snmp_get, mib='IF-MIB',
                                                  index=if_index)
                    if_speed = if_speed + ' Mb/s'
                    all_uplinks.append((if_descr, if_speed))
            device.uplinks = all_uplinks
            logging.info('{} ----> {}'.format(host, device.model))
        else:
            logging.info('{} unrecognized...'.format(host))
        queue.task_done()

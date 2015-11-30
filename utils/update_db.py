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


# Retrive all cards one when module imported
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


class Device(Persistent):
    '''Device representation class

    class attrs:
        num_instances - all created instances (represent new hosts)
        founded_hosts - all hosts that found on the run
    instance attrs:
        ip - IPv4 address of device
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
        identify
        test_domain_name
        translit_location
        check_host
    '''
    num_instances = 0
    founded_hosts = 0

    def __init__(self, ip):
        '''Initialize vlans and uplinks lists and add 1 to class
        num_instances counters
        Args:
            ip - string representation of device IPv4 address
        No return value
        Overloaded
        '''
        self.ip = ip
        self.vlans = []
        self.uplinks = []
        Device.num_instances += 1

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

    def check_host(self, settings):
        '''Check host on typical errors (contact or location absence
        for example) and logs it
        Args:
            settings - instance of utils.load_settings.Settings
        No return value
        '''
        if not self.location:
            logging.error('{}: System: No location for host'.format(self.ip))
        if not self.contact:
            logging.error('{}: System: No contact for host'.format(self.ip))
        elif not re.match(r'(se|ls|lc)\d@intertax.ru', self.contact.strip()):
            logging.error('{}: System: Not useful contact {}'.format(
                self.ip, self.contact))
        if settings.allowed_vlans:
            out_of_range_vlans = (
                [x for x in self.vlans if int(x) not in settings.allowed_vlans])
            if out_of_range_vlans:
                logging.warning(
                    '{}: VLAN DB: not allowed VLANs {} configured on host.'
                    .format(self.ip, out_of_range_vlans))


def worker(queue, settings, db):
    '''Update database by send request on all suplied hosts. Function designed
    for multithreaded use, so it get hosts from Queue. If host answer on
    sysDescr query, function try to recognize model and update or create new
    record on device in database.
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
        oid, device.location = get_with_send(
            '1.3.6.1.2.1.1.6.0', host.exploded, snmp_get)
        if settings.location != 'straight':
            device.translit_location(settings.location)
        oid, device.contact = get_with_send(
            '1.3.6.1.2.1.1.4.0', host.exploded, snmp_get)
        device.test_domain_name()
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
                if re.match(settings.uplink_pattern, if_descr):
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
        device.check_host(settings)
        devdb[device.ip] = device
        transaction.commit()
        queue.task_done()

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
    num_instances = 0
    founded_hosts = 0

    def __init__(self, ip):
        self.ip = ip
        self.vlans = []
        self.uplinks = []
        Device.num_instances += 1

    def identify(self, descr):
        for card in device_cards:
            if re.search(card['info_pattern'], descr):
                self.vlan_oid = card['vlan_tree']
                self.vtree = True if 'vlan_tree_by_oid' in card else False
                self.firmware_oid = card['firmware_oid']
                return card['model_oid']

    def test_domain_name(self):
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
    """Very strange behavior: PySNMP compile SNMPv2-MIB::sysLocation &
    sysContact into OID without last 0. Second strange thing index=0 doesn't
    work at all. So I use numerical OID to retrive location and contact.
    """
    engine = SnmpEngine()
    while True:
        all_vlans = []
        all_uplinks = []
        connection = db.open()
        dbroot = connection.root()
        host = queue.get()
        if host is None:
            connection.close()
            break
        devdb = dbroot['devicedb']
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

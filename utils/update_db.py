import re
import socket
from pysnmp.hlapi import SnmpEngine
import transaction
from persistent import Persistent
from utils.snmpget import snmp_run, process_output, get_with_send, tree_walk
from utils.load_cards import retrive


class Device(Persistent):
    num_instances = 0
    founded_hosts = 0
    device_cards = retrive()

    def __init__(self, ip):
        self.ip = ip
        self.vlans = []
        self.uplinks = []
        Device.num_instances += 1

    def identify(self, descr):
        for card in Device.device_cards:
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
                if self.ip == return_ip:
                    self.dname_error = None
                else:
                    self.dname_error = 'A record not same as PTR'
            except socket.gaierror:
                self.dname_error = 'No A record on received PTR'
        except socket.herror:
            self.dname_error = 'No PTR record for that host'


def worker(queue, settings, db):
    """Very strange behavior but PySNMP compile SNMPv2-MIB::sysLocation &
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
            print('{} ----> {}'.format(host, device.model))
            print('{} ----> {}'.format(host, device.firmware))
            print('{} ----> {}'.format(host, device.uplinks))
            print('{} ----> {}'.format(host, device.vlans))
        else:
            print('{} unrecognized...'.format(host))
        devdb[device.ip] = device
        transaction.commit()
        queue.task_done()

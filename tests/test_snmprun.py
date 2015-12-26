import unittest
from pysnmp.hlapi import SnmpEngine
import utils.snmpget


class SnmpTest(unittest.TestCase):
    def setUp(self):
        self.config = {}
        with open('tests/test.conf') as test_conf:
            for line in test_conf:
                self.config[line.split('=')[0]] = line.split('=')[1].strip()
        self.engine = SnmpEngine()

    def test_snmp_get(self):
        snmp_get = utils.snmpget.snmp_run(self.engine, self.config['community'],
                                          self.config['ip'],
                                          self.config['fw_oid'])
        er_indication, er_status, er_index, var_binds = next(snmp_get)
        full_oid, firmware = utils.snmpget.process_output(
            er_indication, er_status, er_index, var_binds, self.config['ip'])
        self.assertEqual(firmware, self.config['fw'])
        full_oid, sw_model = utils.snmpget.get_with_send(
            self.config['model_oid'], self.config['ip'], snmp_get)
        self.assertEqual(sw_model, self.config['sw'])

    def test_snmp_bulkget(self):
        count = 0
        snmp_get = utils.snmpget.snmp_run(self.engine, self.config['community'],
                                          self.config['ip'], 'ifAlias',
                                          mib='IF-MIB', action='bulk')
        for er_indication, er_status, er_index, var_binds in snmp_get:
            count += 1
        self.assertGreater(count, 1)

    def test_snmp_next(self):
        count = 0
        snmp_get = utils.snmpget.snmp_run(self.engine, self.config['community'],
                                          self.config['ip'], 'ifOperStatus',
                                          mib='IF-MIB', action='next', index=5)
        while count < 10:
            er_indication, er_status, er_index, var_binds = next(snmp_get)
            count += 1
        self.assertEqual(count, 10)

    def test_snmp_walk(self):
        count = 0
        snmp_get = utils.snmpget.tree_walk(
            self.engine, self.config['community'], self.config['ip'],
            'ifAdminStatus', mib='IF-MIB')
        for oid, value in snmp_get:
            count += 1
        self.assertIn('1.3.6.1.2.1.2.2.1.7', oid)

if __name__ == '__main__':
    unittest.main()

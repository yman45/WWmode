import unittest
from pysnmp.hlapi import SnmpEngine
import utils.snmpget


class DefaultTest(unittest.TestCase):
    def test_nothing(self):
        self.assertTrue(True)


class SnmpTest(unittest.TestCase):
    def test_snmp_get(self):
        config = {}
        with open('tests/test.conf') as test_conf:
            for line in test_conf:
                config[line.split('=')[0]] = line.split('=')[1].strip()
        engine = SnmpEngine()
        snmp_get = utils.snmpget.snmp_run(engine, config['community'],
                                          config['ip'], config['fw_oid'])
        er_indication, er_status, er_index, var_binds = next(snmp_get)
        full_oid, firmware = utils.snmpget.process_output(
            er_indication, er_status, er_index, var_binds, config['ip'])
        self.assertEqual(firmware, config['fw'])
        full_oid, sw_model = utils.snmpget.get_with_send(config['model_oid'],
                                                         config['ip'], snmp_get)
        self.assertEqual(sw_model, config['sw'])

if __name__ == '__main__':
    unittest.main()

import logging
import re
from pysnmp.hlapi import *


m_logger = logging.getLogger('wwmode_app.utils.snmpget')


class SnmpGetter:
    '''Class for retriving params from hosts
    args:
        engine - PySNMP engine
        settings - load_settings.FakeSettings instance
    methods:
        overloaded __init__
        sget_sys_description
        sget_equal
        sget_uplink_list
        sget_vlan_list
    '''
    def __init__(self, engine, settings):
        '''Initialize instance
        args:
            engine - PySNMP engine
            settings - load_settings.FakeSettings instance
        No return value
        overloaded
        '''
        self.engine = engine
        self.settings = settings

    def sget_sys_description(self, ip):
        '''Get host sysDescr value by SNMP get & produce instance snmp_get
        attr. This method must run before any other sget_* method
        args:
            ip - IP address of host
        return:
            value - sysDescr value or None if request failed
        '''
        self.snmp_get = snmp_run(self.engine, self.settings.ro_community, ip,
                                 'sysDescr', mib='SNMPv2-MIB')
        error_indication, error_status, error_index, var_binds = next(
            self.snmp_get)
        oid, value = process_output(error_indication, error_status,
                                    error_index, var_binds, ip)
        return value

    def sget_equal(self, device, param, oid):
        '''Get parameter from host by running SNMP get request & set it to
        device object
        args:
            device - Device object
            param - requested parameter name
            oid - SNMP OID
        No return value
        '''
        oid, result = get_with_send(oid, device.ip, self.snmp_get)
        setattr(device, 'c_' + param, result)

    def sget_uplink_list(self, device, param, oid):
        '''Get list of uplink descriptions and speed of appropriate interface
        from host by running SNMP walk and get requests & set list to device
        object
        args:
            device - Device object
            param - requested parameter name
            oid - SNMP OID
        No return value
        '''
        all_uplinks = []
        for oid, if_descr in tree_walk(self.engine, self.settings.ro_community,
                                       device.ip, 'ifAlias', mib='IF-MIB'):
            if if_descr and re.match(self.settings.uplink_pattern, if_descr):
                if_index = oid.split('.')[-1]
                oid, if_speed = get_with_send('ifHighSpeed', device.ip,
                                              self.snmp_get, mib='IF-MIB',
                                              index=if_index)
                if_speed = if_speed + ' Mb/s'
                all_uplinks.append((if_descr, if_speed))
        setattr(device, 'c_' + param, all_uplinks)

    def sget_vlan_list(self, device, param, oid):
        '''Get list of VLANs from host by running SNMP walk request & set list
        to device object
        args:
            device - Device object
            param - requested parameter name
            oid - SNMP OID
        No return value
        '''
        all_vlans = []
        for oid, vlan in tree_walk(self.engine, self.settings.ro_community,
                                   device.ip, oid):
            if not oid:
                m_logger.warning(
                    'No OID when running tree walk at {} on {}'.format(
                        oid, device.ip))
                continue
            if device.vtree:
                vlan = oid.split('.')[-1]
            if vlan not in self.settings.unneded_vlans:
                all_vlans.append(vlan)
        setattr(device, 'c_' + param, all_vlans)


def snmp_run(engine, community_name, address, oid, mib=None, action='get',
             port=161, index=0):
    '''Create SNMP query generator & yield responses from it.
    Can do GET, BULKGET & NEXT queries. Can receive numerical OID, names of
    MIB & OID or names of MIB & OID + index number from wich to start
    Args:
        engine - instance of pysnmp.hlapi.SnmpEngine class
        community_name - SNMP community for reading
        address - IPv4 address of host
        oid - OID to query for
        mib - MIB to query for (DEFAULT - None)
        action - SNMP action to use:
            get - snmpget (DEFAULT)
            bulk - snmpbulkget
            next - snmpnext
        port - UDP port (DEFAULT - 161)
        index - OID index to query for (DEFAULT - 0)
    Yield:
        SNMP response with contain indication of error, error status,
        error index and response
    '''
    kw_args = {}
    if action == 'bulk':
        command_generator = bulkCmd
        kw_args = {'maxCalls': 10}
    elif action == 'next':
        command_generator = nextCmd
        kw_args = {'lexicographicMode': False}
    else:
        command_generator = getCmd
    if mib and action == 'get':
        object_identity = ObjectIdentity(mib, oid, index)
    elif mib and not oid:
        object_identity = ObjectIdentity(mib)
    elif mib:
        object_identity = ObjectIdentity(mib, oid)
    else:
        object_identity = ObjectIdentity(oid)
    cmd_gen_args = [engine, CommunityData(community_name),
                    UdpTransportTarget((address, port)), ContextData()]
    if command_generator == bulkCmd:
        cmd_gen_args.append(0)
        cmd_gen_args.append(50)
    cmd_gen_args.append(ObjectType(object_identity))
    yield from command_generator(*cmd_gen_args, **kw_args)


def process_output(error_indication, error_status, error_index, var_binds,
                   address):
    '''Get snmp_run output and produce tuple with numerical OID and response.
    Log errors if there are some
    Args:
        error_indication
        error_status
        error_index
        var_binds
        address - IPv4 address of device
    Return:
        full_oid - numerical OID which queried
        value - response on query
    '''
    if error_indication:
        m_logger.debug('{} at {}'.format(error_indication, address))
        return None, None
    elif error_status:
        m_logger.error('{} with {} at {}'.format(
            error_status.prettyPrint(),
            error_index and var_binds[int(error_index)-1][0] or '?', address))
        return None, None
    else:
        full_oid = str(var_binds[0][0])
        value = var_binds[0][1].prettyPrint()
        if value.startswith("b'"):
            value = value[2:].strip("'")
        return full_oid, value


def get_with_send(oid, address, snmp_gen, mib=None, index=None):
    '''Send new query into SNMP GET command generator
    Args:
        oid - OID to query for
        address - IPv4 address of device
        snmp_gen - generator function snmp_run
        mib - MIB to query for (DEFAULT - None)
        index - OID index to query for (DEFAULT - None)
    Return:
        result of snmp_run -> process_output ->
    '''
    object_identity = (mib, oid) if mib else (oid, )
    if index:
        object_identity += (index, )
    error_indication, error_status, error_index, var_binds = snmp_gen.send(
        [ObjectType(ObjectIdentity(*object_identity))])
    return process_output(error_indication, error_status, error_index,
                          var_binds, address)


def tree_walk(engine, community, ip, oid, mib=None):
    '''Simulate SNMP WALK behaviour by creating GETNEXT generator with snmp_run
    function & process it output with process_output function
    Args:
        engine - instance of pysnmp.hlapi.SnmpEngine class
        community - SNMP community for reading
        ip - IPv4 address of host
        oid - OID to query for
        mib - MIB to query for (DEFAULT - None)
    Yield:
        result of snmp_run -> process_output ->
    '''
    kw_args = {'action': 'next'}
    if mib:
        kw_args['mib'] = mib
    snmp_next = snmp_run(engine, community, ip, oid, **kw_args)
    for error_indication, error_status, error_index, var_binds in snmp_next:
        r_oid, value = process_output(error_indication, error_status,
                                      error_index, var_binds, ip)
        yield r_oid, value

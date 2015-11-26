import logging
from pysnmp.hlapi import *


logging.basicConfig(filename='running.log', level=logging.INFO)


def snmp_run(engine, community_name, address, oid, mib=None, action='get',
             port=161, index=0):
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
    if error_indication:
        logging.info('{} at {}'.format(error_indication, address))
        return None, None
    elif error_status:
        logging.error('{} with {} at {}'.format(
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
    object_identity = (mib, oid) if mib else (oid, )
    if index: object_identity += (index, )
    error_indication, error_status, error_index, var_binds = snmp_gen.send(
        [ObjectType(ObjectIdentity(*object_identity))])
    return process_output(error_indication, error_status, error_index,
                          var_binds, address)


def tree_walk(engine, community, ip, oid, mib=None):
    kw_args = {'action': 'next'}
    if mib:
        kw_args['mib'] = mib
    snmp_next = snmp_run(engine, community, ip, oid, **kw_args)
    for error_indication, error_status, error_index, var_binds in snmp_next:
        r_oid, value = process_output(error_indication, error_status,
                                      error_index, var_binds, ip)
        yield r_oid, value

import logging
from pysnmp.hlapi import *


logging.basicConfig(filename='running.log', level=logging.INFO)


def snmp_run(engine, community_name, address, oid, mib=None, action='get',
             port=161, index=0):
    kw_arg = {}
    if action == 'bulk':
        command_generator = bulkCmd
    elif action == 'next':
        command_generator = nextCmd
    else:
        command_generator = getCmd
    if mib and action == 'get':
        obj_id = ObjectIdentity(mib, oid, index)
    elif mib and not oid:
        obj_id = ObjectIdentity(mib)
    elif mib:
        obj_id = ObjectIdentity(mib, oid)
    else:
        obj_id = ObjectIdentity(oid)
    cmd_gen_args = [engine, CommunityData(community_name),
                    UdpTransportTarget((address, port)), ContextData()]
    if command_generator == bulkCmd:
        cmd_gen_args.append(0)
        cmd_gen_args.append(50)
        kw_arg = {'maxCalls': 10}
    cmd_gen_args.append(ObjectType(obj_id))
    yield from command_generator(*cmd_gen_args, **kw_arg)


def process_output(erInd, erStat, erIndex, varBinds, address):
    if erInd:
        logging.info('{} at {}'.format(erInd, address))
        return
    elif erStat:
        logging.error('{} with {} at {}'.format(
            errorStat.prettyPrint(),
            errorIndex and varBinds[int(errorIndex)-1][0] or '?', address))
        return
    else:
        return ' = '.join([x.prettyPrint() for x in varBinds[0]])


def get_with_send(oid, address, snmp_gen, mib=None, index=None):
    obj_id = (mib, oid) if mib else (oid, )
    if index: obj_id += (index, )
    erInd, erStat, erIndex, varBinds = snmp_gen.send(
        [ObjectType(ObjectIdentity(*obj_id))])
    result = process_output(erInd, erStat, erIndex, varBinds, address)
    return result

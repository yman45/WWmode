from pysnmp.entity.rfc3413.onliner import cmdgen

def walk_snmp():
    _cmdgen = cmdgen.CommandGenerator()
    yield from _cmdgen.nextCmd(cmdgen.CommunityData('***REMOVED***'), cmdgen.UdpTransportTarget(('n0.borg15.sw.itax', 161)), '1.3.6.1.2.1.31.1.1.1.18')

for i in walk_snmp():
    print(i)

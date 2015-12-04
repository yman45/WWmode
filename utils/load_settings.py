import os
import os.path
import ipaddress
import logging


m_logger = logging.getLogger('wwmode_app.utils.load_settings')


class Settings:
    '''Application settings representation class
    instance attrs:
        conf_location - path to configuration file
        allowed_params - allowed attribute names (settings parameters)
        subnets - IPv4 subnets where devices must be discovered
        hosts - IPv4 addresses of standalone hosts
        unneded_vlans - VLAN list that don't need to be saved in device record
        allowed_vlans - VLAN list that allowed to be configured on device
        location - indicator of what to do with device location:
            straight - nothing to do
            name of a schema in lexicon/schemas - translit using that schema
    methods:
        overloaded __init__
        load_conf
    '''
    def __init__(self):
        '''Initialize instance with configuration location, allowed
        parameters & empty lists of values
        No args & return value
        Overloaded
        '''
        self.conf_location = os.path.join(os.getcwd(), 'wwmode.conf')
        self.allowed_params = ('num_threads', 'subnet', 'unneded_vlans',
                               'uplink_pattern', 'ro_community', 'location',
                               'allowed_vlans', 'db_name', 'db_tree')
        self.subnets = []
        self.hosts = []
        self.unneded_vlans = []
        self.allowed_vlans = []
        self.location = 'straight'

    def load_conf(self):
        '''Parse configuration file and fill instance with attributes
        No args & return value
        '''
        with open(self.conf_location, 'r', encoding='utf-8') as conf_file:
            for line in conf_file:
                cleaned_line = line.lower().strip().split(' = ')
                parameter, value = cleaned_line
                if parameter.startswith('#'):
                    pass
                elif parameter == 'subnet':
                    self.subnets.append(ipaddress.ip_network(value))
                elif parameter == 'host':
                    self.hosts.append(ipaddress.ip_address(value))
                elif parameter == 'unneded_vlans':
                    self.unneded_vlans.extend(
                        [x.strip() for x in value.split(',')])
                elif parameter == 'allowed_vlans':
                    for prt in value.split(','):
                        if '-' in prt:
                            prt1, prt2 = prt.strip().split('-')
                            self.allowed_vlans.extend(range(int(prt1),
                                                            int(prt2)))
                        else:
                            self.allowed_vlans.append(int(prt.strip()))
                elif parameter in self.allowed_params:
                    self.__setattr__(parameter, value)
                else:
                    m_logger.warning('Unidentified parameter: {}'.format(
                        parameter))

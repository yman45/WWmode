import os
import os.path
import ipaddress
import logging
from .wwmode_exception import WWModeException


m_logger = logging.getLogger('wwmode_app.utils.load_settings')


class NoConfigFileError(WWModeException):
    '''Exception for raising when no config file finded'''
    pass


class Settings:
    '''Application settings representation class
    instance attrs:
        conf_location - path to configuration file
        allowed_params - allowed attribute names (settings parameters)
        subnets - IPv4 subnets where devices must be discovered
        hosts - IPv4 addresses of standalone hosts
        unneded_vlans - VLAN list that don't need to be saved in device record
        location - indicator of what to do with device location:
            straight - nothing to do
            name of a schema in lexicon/schemas - translit using that schema
        domain_prefix - prefix for domain name
        default_zone - suffix for domain name (domain zone)
    instance attrs witch assigned by load_conf method described in app docs
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
                               'db_name', 'db_tree', 'supply_zone',
                               'default_zone', 'default_role',
                               'domain_prefix')
        self.subnets = []
        self.hosts = []
        self.unneded_vlans = []
        self.location = 'straight'
        self.domain_prefix = ''
        self.default_zone = ''

    def load_conf(self):
        '''Parse configuration file and fill instance with attributes
        No args & return value
        '''
        try:
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
                    elif parameter in self.allowed_params:
                        self.__setattr__(parameter, value)
                    else:
                        m_logger.warning('Unidentified parameter: {}'.format(
                            parameter))
        except FileNotFoundError:
            er_msg = 'No config file found at {}'.format(self.conf_location)
            m_logger.error(er_msg)
            raise NoConfigFileError(er_msg)

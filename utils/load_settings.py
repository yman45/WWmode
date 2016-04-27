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
        self.allowed_params = ('num_threads', 'unneded_vlans', 'wanted_attrs',
                               'uplink_pattern', 'ro_community', 'location',
                               'db_name', 'db_tree', 'supply_zone',
                               'default_zone', 'default_role', 'domain_prefix')
        self.general = SettingsGroup()
        self.general.location = 'straight'
        self.general.domain_prefix = ''
        self.general.default_zone = ''

    def load_conf(self):
        '''Parse configuration file and fill instance with attributes
        No args & return value
        '''
        try:
            with open(self.conf_location, 'r', encoding='utf-8') as conf_file:
                group = self.general
                for line in conf_file:
                    line = line.strip()
                    if line.startswith('[') and line.endswith(']'):
                        group_name = line.strip('[]')
                        if not hasattr(self, group_name):
                            setattr(self, group_name, SettingsGroup())
                        group = getattr(self, group_name)
                        continue
                    elif not line:
                        continue
                    splitted_line = line.split(' = ')
                    parameter, value = splitted_line
                    parameter = parameter.lower()
                    if parameter.startswith('#'):
                        continue
                    elif parameter in ['subnet', 'host']:
                        if group == self.general:
                            m_logger.warning('Hosts addition in general group')
                        else:
                            getattr(group, parameter + 's').append(
                                ipaddress.ip_network(value))
                    elif parameter == 'unneded_vlans':
                        getattr(group, parameter).extend(
                            [x.strip() for x in value.split(',')])
                    elif parameter == 'wanted_attrs':
                        getattr(group, parameter).append(value)
                    elif parameter in (self.allowed_params +
                                       group.allowed_params):
                        setattr(group, parameter, value)
                    else:
                        m_logger.warning('Unidentified parameter: {}'.format(
                            parameter))
        except FileNotFoundError:
            er_msg = 'No config file found at {}'.format(self.conf_location)
            m_logger.error(er_msg)
            raise NoConfigFileError(er_msg)


class SettingsGroup:
    def __init__(self):
        self.allowed_params = ('subnet', 'host')
        self.unneded_vlans = []
        self.subnets = []
        self.hosts = []
        self.wanted_attrs = []

import os
import os.path
import ipaddress
import logging
from .wwmode_exception import WWModeException


m_logger = logging.getLogger('wwmode_app.utils.load_settings')


class SettingsLoaderException(WWModeException):
    '''Module top level exception'''
    pass


class NoConfigFileError(SettingsLoaderException):
    '''Exception for raising when no config file found'''
    pass


class DuplicateGroupNames(SettingsLoaderException):
    '''Exception for raising when duplicate group names found'''
    pass


class CommonSettings:
    '''Objects with sane default settings for scan start. Used only for
    inheritance.
    No methods
    attributes:
        num_threads (default - 1) - parallel working threads, which taking part
            in scanning
        unneded_vlans (default - []) - list of VLANs that would be omitted from
            DB
        uplink_pattern (default - 'up .+') - string pattern for uplink
            interface description searching
        ro_community (default - 'public') - SNMP community for reading
        location_transliteration (default - 'straight') - transliterate or not
            locations to russian (and which schema to use)
        db_name (default - hosts_db) - database filename
        db_tree (default - hosts) - name of a tree in DB
        supply_zone (default - None) - domain zone to check for supply devices
        default_zone (default - 'local') - domain zone of hosts
        domain_prefix (default - '') - prefix for shortening hosts domain names
        wanted_params (see default in code or in manual) - dictionary with
            parameters to retrive from hosts
    '''
    num_threads = 1
    unneded_vlans = []
    uplink_pattern = 'up .+'
    ro_community = 'public'
    location_transliteration = 'straight'
    db_name = 'hosts_db'
    db_tree = 'hosts'
    supply_zone = None
    default_zone = 'local'
    domain_prefix = ''
    wanted_params = {'model': 'equal',
                     'firmware': 'equal',
                     'uplinks': 'uplink_list'
                     }


class GroupSettings:
    '''Objects for storing group settings.
    methods:
        overloaded __init__
        num_threads (property getter)
        db_name (property getter)
        db_tree (property getter)
        wanted_params (property getter)
    instance attrs:
        group_name - name of the group
        subnets - subnets that are members of the group
        hosts - hosts that are members of the group
        group_wanted - dictionary with parameters to retrive from hosts only
            for that group
    '''
    def __init__(self, group_name):
        '''Initialize group_name and empty instance attributes (subnets, hosts
        and group_wanted. Also add 'private' num_threads, db_name, db_tree and
        wanted_params for use in properties
        Args:
            group_name - name of the group
        No return value
        Overloaded
        '''
        self.group_name = group_name
        self.subnets = []
        self.hosts = []
        self.group_wanted = {}


class AppSettings(CommonSettings):
    '''Application settings representation class
    instance attrs:
        conf_location - path to configuration file
        groups (default - {}) - disctionary for host groups
    methods:
        overloaded __init__
        load_conf
    '''
    def __init__(self):
        '''Initialize instance with configuration location and group list
        No args & return value
        Overloaded
        '''
        self.conf_location = os.path.join(os.getcwd(), 'wwmode.conf')
        self.groups = {}

    def load_conf(self):
        '''Parse configuration file and fill instance with attributes
        No args & return value
        '''
        group = self
        in_wanted = False
        try:
            with open(self.conf_location, 'r', encoding='utf-8') as conf_file:
                for line in conf_file:
                    line = line.rstrip('\n')
                    if line.startswith('[') and line.endswith(']'):
                        group_name = line.strip('[]')
                        if group_name not in self.groups.keys():
                            group = GroupSettings(group_name)
                            self.groups[group_name] = group
                        else:
                            er_msg = 'Duplicate group names found - {}'.format(
                                group_name)
                            m_logger.critical(er_msg)
                            raise DuplicateGroupNames(er_msg)
                    elif not line or line.startswith('#'):
                        pass
                    elif line.rstrip() == 'Wanted:':
                        in_wanted = True
                    else:
                        if in_wanted and not line.startswith((' ', '\t')):
                            in_wanted = False
                        self.parse_param(line.strip(), group, in_wanted)
        except FileNotFoundError:
            er_msg = 'No config file found at {}'.format(self.conf_location)
            m_logger.error(er_msg)
            raise NoConfigFileError(er_msg)

    def parse_param(self, line, group, in_wanted):
        '''Parse parameters from lines
        arguments:
            line - line of configuration stripped of whitespaces
            group - current configurating group
            in_wanted - is that parameter for retriving from hosts
        No return value
        '''
        def parse_wanted(group, parameter, value):
            '''Supporting function for parsing parameters for retriving from
            hosts
            arguments:
                group - current configurating group
                parameter - parameter name
                value - parameter value
            No return value
            '''
            if group == self:
                wanted_dict = self.wanted_params
            else:
                wanted_dict = group.group_wanted
            if parameter in ['contact', 'location', 'model', 'firmware',
                             'uplinks']:
                m_logger.warning("Default parameter '{}' reassignment".format(
                    parameter))
            else:
                wanted_dict[parameter] = value

        def parse_normal(group, parameter, value):
            '''Supporting function for parsing common parameters
            arguments:
                group - current configurating group
                parameter - parameter name
                value - parameter value
            No return value
            '''
            if parameter in ['subnet', 'host']:
                if group == self:
                    m_logger.warning(
                        'Hosts addition without group declaration')
                else:
                    getattr(group, parameter + 's').append(
                        ipaddress.ip_network(value))
            elif parameter == 'unneded_vlans':
                getattr(group, parameter).extend(
                    [x.strip() for x in value.split(',')])
            elif hasattr(group, parameter):
                try:
                    setattr(group, parameter, value)
                except AttributeError:
                    m_logger.warning(
                        'Parameter {} unallowed inside groups'.format(
                            parameter))
            else:
                m_logger.warning('Unidentified parameter: {}'.format(
                    parameter))

        splitted_line = line.split(' = ')
        parameter, value = splitted_line
        parameter = parameter.lower()
        if in_wanted:
            parse_wanted(group, parameter, value)
        else:
            parse_normal(group, parameter, value)


class FakeSettings:
    '''Proxy object for getting settings from instance of AppSettings or
    GroupSettings, with preference for latter
    args:
        app_settings - AppSettings instance
        group_settings - GroupSetting instance
    methods:
        overloaded __init__
        overloaded __getattr__
    '''
    def __init__(self, app_settings, group_settings):
        '''Intialize instance
        attrs:
            app_settings - AppSettings instance
            group_settings - GroupSetting instance
        No return value
        Overloaded
        '''
        self.app_settings = app_settings
        self.group_settings = group_settings

    def __getattr__(self, attr):
        '''Reroute get requests to GroupSettings instance or to AppSettings
        instance if no attribute in former
        args:
            attr - attribute name
        return:
            attribute from on of instances
        '''
        if hasattr(self.group_settings, attr):
            return getattr(self.group_settings, attr)
        else:
            return getattr(self.app_settings, attr)

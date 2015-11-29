import os
import os.path
import ipaddress
import logging


m_logger = logging.getLogger('wwmode_app.utils.load_settings')


class Settings:
    def __init__(self):
        self.conf_location = os.path.join(os.getcwd(), 'wwmode.conf')
        self.allowed_params = ('num_threads', 'subnet', 'unneded_vlans',
                               'uplink_pattern', 'ro_community', 'location')
        self.subnets = []
        self.unneded_vlans = []
        self.location = 'straight'

    def load_conf(self):
        with open(self.conf_location, 'r', encoding='utf-8') as conf_file:
            for line in conf_file:
                cleaned_line = line.lower().strip().split(' = ')
                parameter, value = cleaned_line
                if parameter.startswith('#'):
                    pass
                elif parameter == 'subnet':
                    self.subnets.append(ipaddress.ip_network(value))
                elif parameter == 'unneded_vlans':
                    self.unneded_vlans.extend(
                        [x.strip() for x in value.split(',')])
                elif parameter in self.allowed_params:
                    self.__setattr__(parameter, value)
                else:
                    m_logger.warning('Unidentified parameter: {}'.format(
                        parameter))

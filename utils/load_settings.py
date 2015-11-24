import os
import os.path
import ipaddress
import logging


logging.basicConfig(filename='running.log', level=logging.INFO)


class Settings:
    def __init__(self):
        self.conf_location = os.path.join(os.getcwd(), 'wwmode.conf')
        self.allowed_params = ('num_threads', 'subnet', 'unneded_vlans',
                               'uplink_pattern', 'ro_community')
        self.subnets = []
        self.unneded_vlans = []

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
                    logging.warning('Unidentified parameter: {}'.format(
                        parameter))

import logging
import logging.handlers
from argparse import ArgumentParser
from utils import maintools

parser = ArgumentParser()
action = parser.add_mutually_exclusive_group(required=True)
action.add_argument('-U', '--update', dest='action', action='store_const',
                    const='update', help='start DB update procedure')
action.add_argument('-S', '--show', dest='action', action='store_const',
                    const='show', help='fetch info about devices & print it')
action.add_argument('-G', '--generate', dest='action', action='store_const',
                    const='generate', help='generate usefull lists from DB')
action.add_argument('-E', '--dry-run', dest='action', action='store_const',
                    const='dry_run', help='parse config and print it')
group_s = parser.add_argument_group('-S', 'show options')
group_s.add_argument('-a', '--show-all', dest='show_all', action='store_true',
                     help='show all devices in compressed fashion')
group_s.add_argument('-d', '--device', dest='show_dev', metavar='DEVICE',
                     help='show full device card chosen by FQDN or IP')
group_s.add_argument('-i', '--inactive', dest='inactive', action='store_true',
                     help='show devices that was not found in last update')
group_s.add_argument('-c', '--chain', dest='uplink_chain',
                     metavar='DEVICE', help='show device uplink chain')
group_s.add_argument('-l', '--vlan-chain', dest='find_vlan', metavar='VLAN',
                     help='show devices chain with VLAN configured')
group_s.add_argument(
    '-f', '--full-search', dest='full_search', metavar='SEARCH',
    help='show compressed device cards where SEARCH was found')
group_s.add_argument('-m', '--model', dest='model_search', metavar='MODEL',
                     help='show devices wich model name contain MODEL')
group_s.add_argument('-t', '--older-than', dest='older_software',
                     metavar=('MODEL', 'VERSION'), nargs=2,
                     help='''show all switches of MODEL with older VERSION of
                     software''')
group_s.add_argument('-o', '--outdated', dest='outdated', action='store_true',
                     help='show devices with outdated software')
group_s.add_argument('-p', '--purge', dest='purge', metavar='IP',
                     help='delete device by IP')
group_g = parser.add_argument_group('-G', 'generate option')
group_g.add_argument('-P', '--plain', dest='plain', action='store_true',
                     help='generate plain list of hosts')
group_g.add_argument('-N', '--nagios', dest='nagios', action='store_true',
                     help='generate list of hosts for Nagios')
group_g.add_argument('-D', '--dns', dest='dns', action='store_true',
                     help='generate list of hosts for DNS')
group_g.add_argument('-T', '--trac', dest='trac', action='store_true',
                     help='generate list of hosts for Trac knowledge base')
group_g.add_argument('-R', '--rancid', dest='rancid', action='store_true',
                     help='generate list of hosts for RANCID')
parser.add_argument('-v', '--verbose', dest='verbose', action='count',
                    help='verbose output into console; upto -vv')
args = parser.parse_args()

logger = logging.getLogger('wwmode_app')
logger.setLevel(logging.DEBUG)
if args.action == 'update':
    fh = logging.handlers.RotatingFileHandler(
        'logs/update_db.log', maxBytes=10000000, backupCount=9,
        encoding='utf-8')
else:
    fh = logging.FileHandler('logs/queries.log')
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
if args.verbose:
    if args.verbose > 1:
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)
else:
    ch.setLevel(logging.ERROR)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    '%d %B %Y %H:%M:%S.%03d')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(ch)


def update_cmd():
    '''Interlayer function for different update command execution
    based on provided CLI args
    '''
    maintools.update_db_run()


def show_cmd():
    '''Interlayer function for different show command execution
    based on provided CLI args
    '''
    if args.show_all:
        maintools.show_all_records()
    elif args.show_dev:
        maintools.show_single_device(args.show_dev)
    elif args.inactive:
        maintools.show_all_records(inactive=True)
    elif args.uplink_chain:
        maintools.go_high(args.uplink_chain)
    elif args.find_vlan:
        maintools.search_db('c_vlans', args.find_vlan)
    elif args.model_search:
        maintools.search_db('c_model', args.model_search)
    elif args.full_search:
        maintools.search_db('full', args.full_search)
    elif args.older_software:
        maintools.software_search(*args.older_software)
    elif args.outdated:
        for model, version in maintools.find_newest_firmware():
            maintools.software_search(model, version)
    elif args.purge:
        maintools.delete_record(args.purge)


def generate_cmd():
    '''Interlayer function for different generate command execution
    based on provided CLI args
    '''
    if args.plain:
        maintools.generate_plain_list()
    elif args.dns:
        maintools.generate_dns_list()
    elif args.nagios:
        maintools.generate_nagios_list()
    elif args.rancid:
        maintools.generate_rancid_list()
    elif args.trac:
        maintools.generate_trac_table()


def dry_run_cmd():
    '''Interlayer function for dry run
    '''
    maintools.dry_run()

action_dict = {
    'update': update_cmd,
    'show': show_cmd,
    'generate': generate_cmd,
    'dry_run': dry_run_cmd
}
action_dict[args.action]()

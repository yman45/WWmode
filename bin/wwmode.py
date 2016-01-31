import logging
from argparse import ArgumentParser
from utils import maintools

logger = logging.getLogger('wwmode_app')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('logs/devdb.log')
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    '%d %B %Y %H:%M:%S.%03d')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(ch)

parser = ArgumentParser(allow_abbrev=False)
action = parser.add_mutually_exclusive_group(required=True)
action.add_argument('-U', '--update', dest='action', action='store_const',
                    const='update', help='start DB update procedure')
action.add_argument('-S', '--show', dest='action', action='store_const',
                    const='show', help='show information about devices')
action.add_argument('-F', '--find', dest='action', action='store_const',
                    const='find', help='search device cards in DB')
action.add_argument('-G', '--generate', dest='action', action='store_const',
                    const='generate', help='generate usefull info from DB')
group_s = parser.add_argument_group('-S', 'show options')
group_s.add_argument('-a', '--all', dest='show_all', action='store_true',
                     help='show all devices in compressed fashion')
group_s.add_argument('-d', '--device', dest='show_dev', metavar='DEVICE',
                     help='show full device card chosen by FQDN or IP')
group_s.add_argument('-i', '--inactive', dest='inactive', action='store_true',
                     help='show devices that was not found by last update')
group_s.add_argument('-u', '--uplink-chain', dest='uplink_chain',
                     metavar='DEVICE', help='print device uplink chain')
group_f = parser.add_argument_group('-F', 'find options')
group_f.add_argument('-v', '--find-vlan', dest='find_vlan', metavar='VLAN',
                     help='show all switches with VLAN configured')
group_f.add_argument('-f', '--full-search', dest='full_search',
                     metavar='SEARCH',
                     help='show compressed device cards where SEARCH was found')
group_f.add_argument('-o', '--older-software', dest='older_software',
                     metavar=('MODEL', 'VERSION'), nargs=2,
                     help='''show all switches of MODEL with older VERSION of
                     software''')
group_f.add_argument('-n', '--newer-software', dest='newer_software',
                     metavar=('MODEL', 'VERSION'), nargs=2,
                     help='''show all switches of MODEL with newer VERSION of
                     software''')
group_f.add_argument('-t', '--outdated', dest='outdated', action='store_true',
                     help='show devices with outdated software')
group_g = parser.add_argument_group('-G', 'generate option')
group_g.add_argument('--tacacs', dest='tacacs', action='store_true',
                     help='generate list of hosts for tacacs')
args = parser.parse_args()


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


def find_cmd():
    '''Interlayer function for different find command execution
    based on provided CLI args
    '''
    if args.find_vlan:
        maintools.search_db('vlans', args.find_vlan)
    elif args.full_search:
        maintools.search_db('full', args.full_search)
    elif args.older_software:
        maintools.software_search(*args.older_software)
    elif args.newer_software:
        maintools.software_search(*args.newer_software, older=False)
    elif args.outdated:
        for model, version in maintools.find_newest_firmware():
            maintools.software_search(model, version)


def generate_cmd():
    '''Interlayer function for different generate command execution
    based on provided CLI args
    '''
    if args.tacacs:
        maintools.generate_tacacs_list()

action_dict = {
    'update': update_cmd,
    'show': show_cmd,
    'find': find_cmd,
    'generate': generate_cmd
}
action_dict[args.action]()

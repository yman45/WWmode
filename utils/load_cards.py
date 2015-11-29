import logging
import os
import os.path
import json

m_logger = logging.getLogger('wwmode_app.utils.load_cards')


class NoDeviceDirectoryError(OSError):
    pass


class NoCardsError(OSError):
    pass


def check_dir(dir_name, cards, path_obj='directory'):
    path = os.path.join(os.getcwd(), dir_name)
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        if os.path.isdir(item_path) and path_obj == 'directory':
            check_dir(item_path, cards, path_obj='file')
        elif os.path.isfile(item_path) and path_obj == 'directory':
            m_logger.warning("File {} found in undesirable directory {}".format(
                os.path.basename(item_path), os.path.dirname(item_path)))
        elif os.path.isdir(item_path) and path_obj == 'file':
            m_logger.warning("Directory {} found in undesireable directory {}".
                             format(os.path.basename(item_path),
                                    os.path.dirname(item_path)))
        elif (os.path.isfile(item_path) and path_obj == 'file' and
              os.path.splitext(item_path)[1] != '.json'):
            m_logger.warning(
                'File {} with undesirable extention found in a directory {}'.
                format(os.path.basename(item_path), os.path.dirname(item_path)))
        elif os.path.isfile(item_path) and path_obj == 'file':
            with open(item_path, 'r', encoding='utf-8') as device_card_json:
                try:
                    device_card = dict(json.loads(device_card_json.read()))
                    cards.append(device_card)
                except ValueError:
                    m_logger.error('JSON file {} is corrupted'.format(
                        os.path.basename(item_path)))
                    continue
        else:
            m_logger.warning("Unrecognized item {}".format(item_path))


def retrive():
    cards_path = os.path.join(os.getcwd(), 'dev_cards')
    if not os.path.isdir(cards_path):
        m_logger.warning("No directory with cards founded")
        raise NoDeviceDirectoryError("Directory with cards not found")
    else:
        cards = []
        check_dir(cards_path, cards)
        if not cards:
            m_logger.error("No switch cards retrived")
            raise NoCardsError(
                "No switch cards retrived, check your dev_cards directory")
        else:
            return cards

import logging
from collections import OrderedDict
import os.path
from utils.wwmode_exception import WWModeException


m_logger = logging.getLogger('wwmode_app.lexicon.translate')


class SchemaDoesNotExist(WWModeException):
    '''Exception to be raised when file with schema does not found'''
    pass


class ConvertParametersError(WWModeException):
    '''Exception for invalid parameters for convertion'''
    pass


class DictionaryBuildError(WWModeException):
    '''Exception for invalid file format which not allowed to build
    dictionary from schema file
    '''
    pass


def convert(text, conv_from='cyr', start=0, end=0, schema='iso9_system_A',
            dict_direction='standart', separator=' = '):
    '''Generic function to transliterate a text string
    Args:
        text - string to translit
        conv_from - option for swapping values inside mapping dict ('cyr' for
            'cyr': 'lat' mapping or other for 'lat': 'cyr') (DEFAULT - 'cyr')
        start - from where to start in string (DEFAULT - 0,
            start from first char)
        end - where to end transliteration (DEFAULT - 0, end at the
            end of string)
        schema - filename in schemas directory which contain schema
        dict_direction - option for swapping values while get them from file
            (use 'standart' for default or any other value for swap)
        separator - sign that separate values in file
    Return:
        result of translit function - transliterated text
    '''
    if conv_from not in ['cyr', 'lat']:
        m_logger.warning("""Warning: unknown option {} for conv_from parameter.
                         Using cyr instead""".format(conv_from))
        conv_from = 'cyr'
    if dict_direction not in ['standart', 'reverse']:
        m_logger.warning("""Warning: unknown option {} for dict_direction
                         parameter. Using standart instead""".format(
                             dict_direction))
        dict_direction = 'standart'
    if not type(start) is int or not type(end) is int:
        m_logger.error('Error: start and end parameters must be a digits!')
        raise ConvertParametersError(
            'Start and end parameters must be a digits!')
    if end == 0:
        end = len(text)
    if end > len(text):
        m_logger.warning("""Warning: end parameter bigger than text length.
                         Set end to text end.""")
        end = len(text)
    if end < start:
        m_logger.warning('Warning: start parameter lesser than end. Swap it!')
        end, start = start, end
    if not os.path.exists('lexicon/schemas/'+schema):
        m_logger.error('Error: given schema filename does not exist!')
        raise SchemaDoesNotExist('Given schema filename does not exist!')
    translate_dictionary = build_dict(conv_from, schema,
                                      dict_direction, separator)
    return translit(text, start, end, translate_dictionary)


def build_dict(conv_from, schema, dict_direction, separator):
    '''Build a mapping using for transliteration
    Args:
        conv_from - option for swapping values inside output dict ('cyr' for
            'cyr': 'lat' mapping or other for 'lat': 'cyr')
        schema - file containing transliteration schema
        dict_direction - option for swapping values (use 'standart' for default
            or any other value for swap)
        separator - sign that separate values in file
    Return:
        ordered_translate_dict - OrderedDict containing transliteration mapping
    '''
    translate_dict = []
    with open('lexicon/schemas/'+schema, 'r',
              encoding='utf-8') as schema_file:
        translate_dict_raw = schema_file.read()
    try:
        for line in translate_dict_raw[:-1].split('\n'):
            splitline = line.split(separator)
            if dict_direction == 'standart':
                cyr, lat = splitline[0], splitline[1]
            else:
                cyr, lat = splitline[1], splitline[0]
            if conv_from == 'cyr':
                translate_dict.append((cyr, lat))
            else:
                translate_dict.append((lat, cyr))
    except IndexError:
        m_logger.error(
            'Error: dictionary cat not be build. Check the file format.')
        raise DictionaryBuildError(
            'Dictionary cat not be build. Check the file format.')
    translate_dict = sorted(translate_dict, key=lambda combo: len(combo[0]))
    ordered_translate_dict = OrderedDict()
    for combo in reversed(translate_dict):
        ordered_translate_dict[combo[0]] = combo[1]
    return ordered_translate_dict


def translit(text, start, end, dictionary):
    '''Transliterate string from start index to end using given schema
    Args:
        text - string to translit
        start - start index
        end - end index
        dictionary - transliteration schema biulded by build_dict function
    Return:
        transliterated string
    '''
    first_part = text[:start]
    last_part = text[end:]
    text = text[start:end]
    case_map = [0 if ch.islower() else 1 for ch in text]
    text = text.lower()
    for letters in dictionary.keys():
        if letters in text:
            while text.find(letters) != -1:
                ind = text.index(letters)
                if case_map[ind] == 1:
                    new_letters = dictionary[letters].capitalize()
                else:
                    new_letters = dictionary[letters]
                if len(new_letters) > 1:
                    for x in range(0, len(new_letters)-1):
                        case_map.insert(ind, 'i')
                if len(letters) > 1:
                    text = text[:ind] + text[ind+len(letters)-1:]
                    del case_map[ind:ind+len(letters)-1]
                text = text[:ind] + new_letters + text[ind+1:]
    return first_part + text + last_part

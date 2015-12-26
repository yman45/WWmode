import unittest
import os
import os.path
from utils.load_settings import Settings, NoConfigFileError

class LoadSettingsTest(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()
        self.conf_location = os.path.join(os.getcwd(), 'tests/fake.conf')

    def test_no_config_file(self):
        self.settings.conf_location = 'unusefull_path/unusefull.conf'
        self.assertRaises(NoConfigFileError, self.settings.load_conf)

    def test_unusefull_param(self):
        self.settings.load_conf()
        self.assertRaises(AttributeError, getattr, *[self.settings, 'hat'])

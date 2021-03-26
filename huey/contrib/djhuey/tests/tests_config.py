import unittest
from unittest.mock import patch

from huey import RedisHuey, MemoryHuey
from huey.exceptions import ConfigurationError
from huey.contrib.djhuey.config import DjangoHueySettingsReader

class DjHueyTests(unittest.TestCase):
    def test_djhuey_config_with_no_settings(self):
        config = DjangoHueySettingsReader(None, None)

        self.assertFalse(config.is_single_queue)
        self.assertFalse(config.is_multi_queue)

    def test_djhuey_config_with_huey_setting(self):
        HUEY = {
            'name': 'test',
            'always_eager': True,
        }
        config = DjangoHueySettingsReader(HUEY, None)

        self.assertTrue(config.is_single_queue)
        self.assertFalse(config.is_multi_queue)

    def test_djhuey_config_with_hueys_setting(self):
        HUEYS = {
            'queuename': {
                'name': 'test',
                'always_eager': True,
            }
        }
        config = DjangoHueySettingsReader(None, HUEYS)

        self.assertFalse(config.is_single_queue)
        self.assertTrue(config.is_multi_queue)

    def test_djhuey_configure_raises_error_when_both_settings_are_defined(self):
        HUEY = {
            'name': 'test',
            'always_eager': True,
        }

        HUEYS = {
            'queuename': {
                'name': 'test',
                'always_eager': True,
            }
        }
        config = DjangoHueySettingsReader(HUEY, HUEYS)

        with self.assertRaises(ConfigurationError):
            config.configure()

    def test_djhuey_configure_is_redis_huey_when_no_setting_is_defined(self):
        config = DjangoHueySettingsReader(None, None)

        config.configure()

        self.assertTrue(isinstance(config.huey_setting, RedisHuey))
        self.assertEquals(config.huey_setting.name, 'test')


    def test_djhuey_configure_when_huey_setting_is_defined(self, *args):
        HUEY = {
            'huey_class': 'huey.RedisHuey',  # Huey implementation to use.
            'name': 'testname',  # Use db name for huey.
        }

        config = DjangoHueySettingsReader(HUEY, None)

        config.configure()

        self.assertTrue(isinstance(config.huey_setting, RedisHuey))
        self.assertEquals(config.default_queue(None).name, 'testname')

    def test_djhuey_configure_when_hueys_setting_is_defined(self, *args):
        HUEYS = {
            'first': {
                'huey_class': 'huey.RedisHuey',  # Huey implementation to use.
                'name': 'testname',  # Use db name for huey.
            },
            'mails': {
                'huey_class': 'huey.MemoryHuey',  # Huey implementation to use.
                'name': 'testnamememory',  # Use db name for huey.
            }
        }

        config = DjangoHueySettingsReader(None, HUEYS)

        config.configure()

        self.assertTrue(isinstance(config.default_queue('first'), RedisHuey))
        self.assertEquals(config.default_queue('first').name, 'testname')
        self.assertTrue(isinstance(config.default_queue('mails'), MemoryHuey))
        self.assertEquals(config.default_queue('mails').name, 'testnamememory')

    def test_djhuey_configure_when_hueys_setting_is_defined(self, *args):
        HUEYS = object()

        config = DjangoHueySettingsReader(None, HUEYS)

        with self.assertRaises(SystemExit):
            config.configure()


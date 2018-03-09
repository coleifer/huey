try:
    from unittest.mock import patch
except Exception:
    from mock import patch

from django.test import TestCase

from huey import RedisHuey
from huey.consumer import Consumer
from huey.contrib.djhuey.configuration import SingleConfReader, MultiConfReader, HueySettingsReader
from huey.exceptions import ConfigurationError


class SingleConfReaderTest(TestCase):
    def test_huey(self):
        config = {
            'name': 'myapp',
            'connection': {'host': 'localhost', 'port': 6378},
            'consumer': {
                'workers': 4,
                'worker_type': 'process',  # "thread" or "greenlet" are other options
            },
        }
        huey = SingleConfReader.by_legacy(config).huey
        self.assertIsInstance(huey, RedisHuey)
        self.assertTrue('myapp' in huey.storage.queue_key)
        self.assertEqual(huey.storage.connection_params['host'], 'localhost')
        self.assertEqual(huey.storage.connection_params['port'], 6378)

    def test_read_consumer_options(self):
        config = {
            'name': 'myapp',
            'connection': {'host': 'localhost', 'port': 6379},
            'consumer': {
                'workers': 4,
                'worker_type': 'process',  # "thread" or "greenlet" are other options
            },
        }
        consumer_config = SingleConfReader.by_legacy(config).consumer_options
        self.assertEqual(consumer_config['workers'], 4)
        self.assertEqual(consumer_config['worker_type'], 'process')

    @patch('huey.consumer_options.ConsumerConfig.setup_logger')
    def test_consumer(self, setup_logger):
        config = {
            'name': 'myapp',
            'connection': {'host': 'localhost', 'port': 6379},
            'consumer': {
                'workers': 4,
                'worker_type': 'process',  # "thread" or "greenlet" are other options
            },
        }
        reader = SingleConfReader.by_legacy(config)
        consumer = reader.consumer
        self.assertIsInstance(consumer, Consumer)
        self.assertEqual(consumer.huey, reader.huey)
        self.assertEqual(consumer.workers, 4)

    def test_modern_conf_factory(self):
        config = {
            'connection': {'host': 'localhost', 'port': 6378},
            'consumer': {
                'workers': 4,
                'worker_type': 'process',  # "thread" or "greenlet" are other options
            },
        }
        huey = SingleConfReader.by_modern('myapp', config).huey
        self.assertIsInstance(huey, RedisHuey)
        self.assertTrue('myapp' in huey.storage.queue_key)
        self.assertEqual(huey.storage.connection_params['host'], 'localhost')
        self.assertEqual(huey.storage.connection_params['port'], 6378)

    def test_legacy_in_modern_constructor(self):
        config = {
            'name': 'myapp',
            'connection': {'host': 'localhost', 'port': 6379},
            'consumer': {
                'workers': 4,
                'worker_type': 'process',  # "thread" or "greenlet" are other options
            },
        }
        with self.assertRaises(ValueError):
            SingleConfReader.by_modern('myapp', config)

    def test_modern_in_legacy_constructor(self):
        config = {
            'connection': {'host': 'localhost', 'port': 6378},
            'consumer': {
                'workers': 4,
                'worker_type': 'process',  # "thread" or "greenlet" are other options
            },
        }
        with self.assertRaises(ValueError):
            SingleConfReader.by_legacy('myapp', config)

    def test_factory_usage_forcing(self):
        with self.assertRaises(ValueError):
            SingleConfReader({})


class MultiConfReaderTest(TestCase):
    def setUp(self):
        self.config = {
            'my-app': {
                'backend': 'huey.backends.redis_backend',
                'connection': {'host': 'localhost', 'port': 6378},
                    'consumer': {
                        'workers': 4,
                        'worker_type': 'process',
                }
            },
            'my-app2': {
                'default': True,
                'backend': 'huey.backends.sqlite_backend',
                'connection': {'location': 'sqlite filename'},
                    'consumer': {
                        'workers': 4,
                        'worker_type': 'process',
                }
            },
        }

    def test_configurations_splitting(self):
        reader = MultiConfReader(self.config)
        self.assertEqual(len(reader.configurations), 2)

    def test_huey(self):
        reader = MultiConfReader(self.config)
        huey = reader.configurations[0].huey
        self.assertIsInstance(huey, RedisHuey)
        self.assertTrue('myapp' in huey.storage.queue_key)

    def test_get_item(self):
        reader = MultiConfReader(self.config)
        conf = reader['my-app']
        self.assertEqual(conf.name, 'my-app')

    def test_default_config(self):
        reader = MultiConfReader(self.config)
        conf = reader.default_configuration
        self.assertEqual(conf.name, 'my-app2')

    def test_no_default_config(self):
        config = {
            'my-app': {
                'backend': 'huey.backends.redis_backend',
                'connection': {'host': 'localhost', 'port': 6378},
                'consumer': {
                    'workers': 4,
                    'worker_type': 'process',
                }
            },
            'my-app2': {
                'backend': 'huey.backends.sqlite_backend',
                'connection': {'location': 'sqlite filename'},
                'consumer': {
                    'workers': 4,
                    'worker_type': 'process',
                }
            },
        }
        reader = MultiConfReader(config)
        conf = reader.default_configuration
        self.assertTrue(conf.name == 'my-app' or conf.name == 'my-app2')

    def test_legacy_in_constructor(self):
        config = {
            'name': 'myapp',
            'connection': {'host': 'localhost', 'port': 6379},
            'consumer': {
                'workers': 4,
                'worker_type': 'process',  # "thread" or "greenlet" are other options
            },
        }
        with self.assertRaises(ValueError):
            MultiConfReader(config)


class HueySettingsReaderTest(TestCase):
    def test_completely_wrong_config(self):
        config = {}
        reader = HueySettingsReader(config)
        with self.assertRaises(ConfigurationError):
            reader.start()

    def test_completely_wrong_config2(self):
        config = {'blabla': 'blabla'}
        reader = HueySettingsReader(config)
        with self.assertRaises(ConfigurationError):
            reader.start()

    def test_read_config(self):
        config = {
            'my-app': {
                'default': True,
                'backend': 'huey.backends.redis_backend',
                'connection': {'host': 'localhost', 'port': 6379},
                'consumer': {
                    'workers': 4,
                    'worker_type': 'process',
                }
            },
            'my-app2': {
                'backend': 'huey.backends.sqlite_backend',
                'connection': {'location': 'sqlite filename'},
                'consumer': {
                    'workers': 4,
                    'worker_type': 'process',
                }
            },
        }
        dh = HueySettingsReader(config)
        dh.start()
        self.assertEqual(dh.huey.name, 'my-app')
        self.assertEqual(len(dh.hueys), 2)

    def test_read_config_legacy(self):
        config = {
            'name': 'my-app',
            'connection': {'host': 'localhost', 'port': 6379},
            'consumer': {
                'workers': 4,
                'worker_type': 'process',  # "thread" or "greenlet" are other options
            },
        }
        dh = HueySettingsReader(config)
        dh.start()
        self.assertEqual(dh.huey.name, 'my-app')
        self.assertEqual(len(dh.hueys), 1)

    def test_task_equal(self):
        def sample_task():
            return 'bla'

        config = {
            'name': 'my-app',
            'connection': {'host': 'localhost', 'port': 6379},
            'always_eager': True,
            'consumer': {
                'workers': 4,
                'worker_type': 'process',  # "thread" or "greenlet" are other options
            },
        }
        dh = HueySettingsReader(config)
        dh.start()
        dh_task = dh.task()(sample_task)
        huey_task = dh.huey.task()(sample_task)
        dh_ret = dh_task()
        huey_ret = huey_task()
        self.assertEqual(dh_ret, huey_ret)

    def test_task_equal_choose_name(self):
        def sample_task():
            return 'bla'

        config = {
            'my-app': {
                'default': True,
                'backend': 'huey.backends.redis_backend',
                'always_eager': True,
                'connection': {'host': 'localhost', 'port': 6379},
                'consumer': {
                    'workers': 4,
                    'worker_type': 'process',
                }
            },
            'my-app2': {
                'backend': 'huey.backends.sqlite_backend',
                'connection': {'location': 'sqlite filename'},
                'consumer': {
                    'workers': 4,
                    'worker_type': 'process',
                }
            },
        }
        dh = HueySettingsReader(config)
        dh.start()
        dh_task = dh.task(queue='my-app')(sample_task)
        huey_task = dh.huey.task()(sample_task)
        dh_ret = dh_task()
        huey_ret = huey_task()
        self.assertEqual(dh_ret, huey_ret)



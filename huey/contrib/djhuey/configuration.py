import sys

from django.conf import settings

from huey import RedisHuey
from huey.consumer import Consumer
from huey.consumer_options import ConsumerConfig
from huey.exceptions import ConfigurationError

configuration_message = """
Configuring Huey for use with Django
====================================

Huey was designed to be simple to configure in the general case.  For that
reason, huey will "just work" with no configuration at all provided you have
Redis installed and running locally.

On the other hand, you can configure huey manually using the following
setting structure.

The following example uses Redis on localhost, and will run four worker
processes:

HUEY = {
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

Additionally the old configuration variant is still usable:

HUEY = {
    'name': 'my-app',
    'connection': {'host': 'localhost', 'port': 6379},
    'consumer': {
        'workers': 4,
        'worker_type': 'process',  # "thread" or "greenlet" are other options
    },
}

If you would like to configure Huey's logger using Django's integrated logging
settings, the logger used by consumer is named "huey.consumer".

Alternatively you can simply assign `settings.HUEY` to an actual `Huey`
object instance:

from huey import RedisHuey
HUEY = RedisHuey('my-app')
"""


def default_queue_name():
    try:
        return settings.DATABASE_NAME
    except AttributeError:
        try:
            return settings.DATABASES['default']['NAME']
        except KeyError:
            return 'huey'


def config_error(msg):
    print(configuration_message)
    print('\n\n')
    print(msg)
    sys.exit(1)


class HueySettingsReader:
    def __init__(self, huey_settings):
        self.huey_settings = huey_settings
        self.hueys = {}
        self.huey = None
        self.consumers = {}
        self.consumer = None

    def task(self, name=None, *args, **kwargs):
        if name is None:
            huey = self.huey
        else:
            huey = self.hueys[name]

        return huey.task(*args,**kwargs)

    def periodic_task(self, name=None, *args, **kwargs):
        if name is None:
            huey = self.huey
        else:
            huey = self.hueys[name]

        def decorator(func):
            return huey.periodic_task(*args, **kwargs)(func)

        return decorator

    def _huey_instance_config(self):
        self.huey = self.huey_settings
        self.hueys = {default_queue_name(): self.huey}

    def _no_config(self):
        try:
            from huey import RedisHuey
        except ImportError:
            config_error('Error: Huey could not import the redis backend. '
                         'Install `redis-py`.')
        else:
            self.huey = RedisHuey(default_queue_name())
            self.hueys = {default_queue_name(): self.huey}

    def _single_config(self):
        single_reader = SingleConfReader.by_legacy(self.huey_settings)
        self.huey = single_reader.huey
        self.hueys = {single_reader.name: self.huey}
        self.consumers = {single_reader.name: self.consumer}

    def _multi_config(self):
        multi_reader = MultiConfReader(self.huey_settings)
        self.consumer = multi_reader.default_configuration.consumer

        self.huey = multi_reader.default_configuration.huey
        for single_reader in multi_reader.configurations:
            self.hueys[single_reader.name] = single_reader.huey
            self.consumers[single_reader.name] = single_reader.consumer

    def start(self):
        if self.huey_settings is None:
            self._no_config()
            return
        if isinstance(self.huey_settings, RedisHuey):
            self._huey_instance_config()
            return
        if isinstance(self.huey_settings, dict):
            if SingleConfReader.is_legacy(self.huey_settings):
                self._single_config()
                return
            if MultiConfReader.is_multi_config(self.huey_settings):
                self._multi_config()
                return
        raise ConfigurationError('Configuration doesnt match guidelines.')



class MultiConfReader:
    """
    Supports the multi queue configuration.
    This configuration style aligns with the django database configuration in the django settings file.
    The reader is lazy. It only creates RedisHuey and Consumer if the properties are accessed.

    HUEY = {
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

    The MultiConfiguration adds a additional property: default.
    It indicates the default queue if only the decorator @huey.task is used.
    The default property can only be used once.
    """

    def __init__(self, huey_settings, handle_options={}):
        self.huey_settings = huey_settings.copy()
        self.handle_options = handle_options
        self._single_conf_readers = []
        self._default_reader = None
        self._create_single_confs()

    @classmethod
    def is_multi_config(cls, huey_settings):
        if SingleConfReader.is_legacy(huey_settings):
            return False
        if len(huey_settings) == 0:
            return False
        first_config = list(huey_settings.values())[0]
        return SingleConfReader.is_modern(first_config)

    def _create_single_confs(self):
        huey_config = self.huey_settings.copy()
        for name, config in huey_config.items():
            reader = SingleConfReader.by_modern(name, config)
            if reader.is_default():
                self._default_reader = reader
            self._single_conf_readers.append(reader)

    def __getitem__(self, item):
        for conf in self._single_conf_readers:
            if conf.name == item:
                return conf
        raise KeyError

    def is_valid(self):
        for key, value in self.huey_settings.items():
            if not isinstance(value, dict):
                return False
        return True

    @property
    def configurations(self):
        return self._single_conf_readers

    @property
    def default_configuration(self):
        if self._default_reader is not None:
            return self._default_reader
        return self._single_conf_readers[0]


class SingleConfReader:
    """
    Supports the old legacy and the modern configuration.
    The reader is lazy. It only creates RedisHuey and Consumer if the properties are accessed.
    """

    def __init__(self, huey_settings, handle_options={}, _factory_call=False):
        if not _factory_call:
            raise ValueError("Use the by_legacy or by_modern factory. Direct use of the constructor is not allowed.")
        self.huey_settings = huey_settings.copy()
        self.handle_options = handle_options
        self._huey = None
        self._consumer = None

    @classmethod
    def is_legacy(cls, huey_settings):
        return 'name' in huey_settings

    @classmethod
    def is_modern(cls, huey_settings):
        return isinstance(huey_settings, dict) and 'name' not in huey_settings

    @classmethod
    def by_legacy(cls, huey_settings, handle_options={}):
        if not cls.is_legacy(huey_settings):
            raise ValueError('huey_settings is not a legacy setting.')
        return cls(huey_settings, handle_options=handle_options, _factory_call=True)

    @classmethod
    def by_modern(cls, name, config, handle_options={}):
        if not cls.is_modern(config):
            raise ValueError('config is a legacy setting.')
        config = config.copy()
        config['name'] = name
        return cls(config, handle_options=handle_options, _factory_call=True)

    @property
    def name(self):
        if 'name' in self.huey_settings:
            return self.huey_settings['name']
        else:
            return ''

    @property
    def huey(self):
        if self._huey is not None:
            return self._huey
        huey_config = self.huey_settings.copy()
        name = huey_config.pop('name', self.default_queue_name())
        conn_kwargs = huey_config.pop('connection', {})
        try:
            del huey_config['consumer']  # Don't need consumer opts here.
        except KeyError:
            pass
        try:
            del huey_config['default']  # Don't need default opt here.
        except KeyError:
            pass
        if 'always_eager' not in huey_config:
            huey_config['always_eager'] = settings.DEBUG
        huey_config.update(conn_kwargs)
        self._huey = RedisHuey(name, **huey_config)
        return self._huey

    @property
    def consumer_options(self):
        consumer_options = {}
        huey_config = self.huey_settings.copy()
        if isinstance(huey_config, dict):
            consumer_options.update(huey_config.get('consumer', {}))

        for key, value in self.handle_options.items():
            if value is not None:
                consumer_options[key] = value

        consumer_options.setdefault('verbose',
                                    consumer_options.pop('huey_verbose', None))
        return consumer_options

    @property
    def consumer(self):
        if self._consumer is not None:
            return self._consumer
        config = ConsumerConfig(**self.consumer_options)
        config.validate()
        config.setup_logger()
        self._consumer = Consumer(self.huey, **config.values)
        return self._consumer

    @staticmethod
    def default_queue_name():
        try:
            return settings.DATABASE_NAME
        except AttributeError:
            try:
                return settings.DATABASES['default']['NAME']
            except KeyError:
                return 'huey'

    def is_default(self):
        if 'default' in self.huey_settings:
            if self.huey_settings['default']:
                return True
        return False

    def __str__(self):
        return str(self.huey_settings)

import sys

from importlib import import_module
from django.conf import settings
from huey.exceptions import ConfigurationError


default_backend_path = 'huey.RedisHuey'

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
    'name': 'my-app',
    'connection': {'host': 'localhost', 'port': 6379},
    'consumer': {
        'workers': 4,
        'worker_type': 'process',  # "thread" or "greenlet" are other options
    },
}

Sometimes you need to configure multiple queues, you can use HUEYS setting for that.

The following example provides two queues. One of them uses Redis on localhost, and will run four worker
processes. The other one will run two worker processes and its intended to be used for emails:

HUEYS = {
    'first': {
        'name': 'my-app',
        'connection': {'host': 'localhost', 'port': 6379},
        'consumer': {
            'workers': 4,
            'worker_type': 'process',  # "thread" or "greenlet" are other options
        }
    },
    'emails': {
        'name': 'email',
        'connection': {'host': 'localhost', 'port': 6379},
        'consumer': {
            'workers': 2,
            'worker_type': 'process',  # "thread" or "greenlet" are other options
        },
    },
}

If you would like to configure Huey's logger using Django's integrated logging
settings, the logger used by consumer is named "huey".

Alternatively you can simply assign `settings.HUEY` to an actual `Huey`
object instance:

from huey import RedisHuey
HUEY = RedisHuey('my-app')
"""




def get_backend(import_path=default_backend_path):
    module_path, class_name = import_path.rsplit('.', 1)
    module = import_module(module_path)
    return getattr(module, class_name)


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

class DjangoHueySettingsReader:
    def __init__(self, huey_setting, hueys_setting):
        self.huey_setting = huey_setting
        self.hueys_setting = hueys_setting

        self.huey = None
        self.hueys = {}


    @property
    def is_single_queue(self):
        return self.huey_setting is not None

    @property
    def is_multi_queue(self):
        return self.hueys_setting is not None
    

    def configure(self):
        if self.is_single_queue and self.is_multi_queue:
            raise ConfigurationError('Error: HUEY and HUEYS settings are incompatible!')

        if not self.is_single_queue and not self.is_multi_queue:
            try:
                RedisHuey = get_backend(default_backend_path)
            except ImportError:
                config_error('Error: Huey could not import the redis backend. '
                             'Install `redis-py`.')
            else:
                self.huey_setting = RedisHuey(default_queue_name())

        if isinstance(self.huey_setting, dict):
            self.huey_setting = self._configure_instance(self.huey_setting.copy())

        if self.is_multi_queue:
            if not isinstance(self.hueys_setting, dict):
                config_error('Error: HUEYS must be a dictionary ')

            new_hueys = dict()
            for queue_name, config in self.hueys_setting.items():
                huey_config = config.copy()

                new_hueys[queue_name] = self._configure_instance(huey_config)

            self.hueys_setting = new_hueys


    def default_queue(self, queue):
        if self.is_multi_queue and queue is None:
            config_error("""
If HUEYS is configured run_huey must receive a --queue parameter
i.e.: 
python manage.py run_huey --queue first
                """)
        return self.huey_setting if self.is_single_queue else self.hueys_setting[queue]


    def _configure_instance(self, huey_config):
        name = huey_config.pop('name', default_queue_name())
        if 'backend_class' in huey_config:
            huey_config['huey_class'] = huey_config.pop('backend_class')
        backend_path = huey_config.pop('huey_class', default_backend_path)
        conn_kwargs = huey_config.pop('connection', {})
        try:
            del huey_config['consumer']  # Don't need consumer opts here.
        except KeyError:
            pass
        if 'immediate' not in huey_config:
            huey_config['immediate'] = settings.DEBUG
        huey_config.update(conn_kwargs)

        try:
            backend_cls = get_backend(backend_path)
        except (ValueError, ImportError, AttributeError):
            config_error('Error: could not import Huey backend:\n%s'
                         % traceback.format_exc())

        return backend_cls(name, **huey_config)

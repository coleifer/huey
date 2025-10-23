import logging
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.module_loading import autodiscover_modules

from huey.consumer_options import ConsumerConfig
from huey.consumer_options import OptionParserHandler


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Queue consumer. Example usage::

    To start the consumer (note you must export the settings module):

    django-admin.py run_huey
    """
    help = "Run the queue consumer"
    _type_map = {'int': int, 'float': float}

    def add_arguments(self, parser):
        option_handler = OptionParserHandler()
        groups = (
            option_handler.get_logging_options(),
            option_handler.get_worker_options(),
            option_handler.get_scheduler_options(),
        )
        for option_list in groups:
            for short, full, kwargs in option_list:
                if short == '-v':
                    full = '--huey-verbose'
                    short = '-V'
                if 'type' in kwargs:
                    kwargs['type'] = self._type_map[kwargs['type']]
                kwargs.setdefault('default', None)
                parser.add_argument(full, short, **kwargs)

        parser.add_argument('-A', '--disable-autoload', action='store_true',
                            dest='disable_autoload',
                            help='Do not autoload "tasks.py"')

    def handle(self, *args, **options):
        from huey.contrib.djhuey import HUEY

        # Python 3.8+ on MacOS uses an incompatible multiprocess model. In this
        # case we must explicitly configure mp to use fork().
        if ((sys.version_info >= (3, 8) and sys.platform == 'darwin') or
            (sys.version_info >= (3, 14))):
            import multiprocessing
            try:
                multiprocessing.set_start_method('fork')
            except RuntimeError:
                pass

        consumer_options = {}
        try:
            if isinstance(settings.HUEY, dict):
                consumer_options.update(settings.HUEY.get('consumer', {}))
        except AttributeError:
            pass

        for key, value in options.items():
            if value is not None:
                consumer_options[key] = value

        consumer_options.setdefault('verbose',
                                    consumer_options.pop('huey_verbose', None))

        if not options.get('disable_autoload'):
            autodiscover_modules("tasks")

        logger = logging.getLogger('huey')

        config = ConsumerConfig(**consumer_options)
        config.validate()

        # Only configure the "huey" logger if it has no handlers. For example,
        # some users may configure the huey logger via the Django global
        # logging config. This prevents duplicating log messages:
        if not logger.handlers:
            config.setup_logger(logger)

        consumer = HUEY.create_consumer(**config.values)
        consumer.run()

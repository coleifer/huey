import logging
import sys
import os
import multiprocessing
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

        # We explicitly set 'fork' on platforms that support it. 
        # On Windows, 'fork' is not available so we skip this
        # entirely — Windows always uses 'spawn' by default.
        if sys.platform != 'win32':
            try:
                if 'fork' in multiprocessing.get_all_start_methods():
                    multiprocessing.set_start_method('fork')
            except RuntimeError:
                # Context already set elsewhere, ignore.
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

        if not options.get('disable_autoload'):
            autodiscover_modules("tasks")
        else:
            # We are notifying Windows child processes not to autoload tasks.py. 
            # This is necessary because the "spawn" start method on Windows causes the child process to re-import the module, 
            # which would trigger autoloading again. By setting
            os.environ['HUEY_DISABLE_AUTOLOAD'] = '1'

        # Only configure the "huey" logger if it has no handlers. For example,
        # some users may configure the huey logger via the Django global
        # logging config. This prevents duplicating log messages:
        if not logger.handlers:
            config.setup_logger(logger)

        os.environ['HUEY_LOGLEVEL'] = str(logger.level)

        # On Windows, process mode uses 'spawn' and must reconstruct the Huey
        # instance inside each child process from scratch (nothing complex is
        # picklable). We tell the consumer where to find HUEY so child
        # processes can re-import it without pickling.
        config.values['huey_import_path'] = 'huey.contrib.djhuey.HUEY'

        consumer = HUEY.create_consumer(**config.values)

        consumer.run()
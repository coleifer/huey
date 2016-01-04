import imp
import sys
from importlib import import_module
from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand

try:
    from django.apps import apps as django_apps
    HAS_DJANGO_APPS = True
except ImportError:
    # Django 1.6
    HAS_DJANGO_APPS = False

from huey.consumer import Consumer
from huey.bin.huey_consumer import get_loglevel
from huey.bin.huey_consumer import setup_logger


class Command(BaseCommand):
    """
    Queue consumer.  Example usage::

    To start the consumer (note you must export the settings module):

    django-admin.py run_huey
    """
    help = "Run the queue consumer"

    option_list = BaseCommand.option_list + (
        make_option('--workers', '-w',
            dest='workers',
            type='int',
            help='Number of worker threads/processes/greenlets'
        ),
        make_option('--worker-type', '-k',
            dest='worker_type',
            help='worker execution model (thread, greenlet, process).',
            default='thread',
            choices=['greenlet', 'thread', 'process', 'gevent'],
        ),
        make_option('--delay', '-d',
            dest='initial_delay',
            type='float',
            help='Delay between polling requests'
        ),
        make_option('--max_delay', '-m',
            dest='max_delay',
            type='float',
            help='Maximum delay between polling requests'
        ),
        make_option('--no-periodic', '-n',
            default=True,
            dest='periodic',
            action='store_false',
            help='Do not enqueue periodic commands'
        ),
    )

    def autodiscover_appconfigs(self):
        """Use Django app registry to pull out potential apps with tasks.py module."""
        module_name = 'tasks'
        for config in django_apps.get_app_configs():
            app_path = config.module.__path__
            try:
                fp, path, description = imp.find_module(module_name, app_path)
            except ImportError:
                continue
            else:
                import_path = '%s.%s' % (config.name, module_name)
                imp.load_module(import_path, fp, path, description)

    def autodiscover_old(self):
        # this is to find modules named <commands.py> in a django project's
        # installed apps directories
        module_name = 'tasks'

        for app in settings.INSTALLED_APPS:
            try:
                import_module(app)
                app_path = sys.modules[app].__path__
            except AttributeError:
                continue
            try:
                imp.find_module(module_name, app_path)
            except ImportError:
                continue
            import_module('%s.%s' % (app, module_name))
            app_path = sys.modules['%s.%s' % (app, module_name)]

    def autodiscover(self):
        """Switch between Django 1.7 style and old style app importing."""
        if HAS_DJANGO_APPS:
            self.autodiscover_appconfigs()
        else:
            self.autodiscover_old()

    def handle(self, *args, **options):
        from huey.contrib.djhuey import HUEY

        consumer_options = {}
        if isinstance(settings.HUEY, dict):
            consumer_options.update(settings.HUEY.get('consumer', {}))

        if options['workers'] is not None:
            consumer_options['workers'] = options['workers']

        if options['worker_type'] is not None:
            consumer_options['worker_type'] = options['worker_type']

        if options['periodic'] is not None:
            consumer_options['periodic'] = options['periodic']

        if options['initial_delay'] is not None:
            consumer_options['initial_delay'] = options['initial_delay']

        if options['max_delay'] is not None:
            consumer_options['max_delay'] = options['max_delay']

        self.autodiscover()

        loglevel = get_loglevel(consumer_options.pop('loglevel', None))
        logfile = consumer_options.pop('logfile', None)
        setup_logger(loglevel, logfile, consumer_options['worker_type'])

        consumer = Consumer(HUEY, **consumer_options)
        consumer.run()

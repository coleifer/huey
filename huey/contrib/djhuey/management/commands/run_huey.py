import imp
import sys
from importlib import import_module
from optparse import make_option

import django
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

class CompatParser(object):
    """Converts argeparse arguments to optparse for Django < 1.8 compatibility."""

    def __init__(self, command):
        self.command = command

    def add_argument(self, *args, **kwargs):
        if 'type' in kwargs:
            # Convert `type=int` to `type="int"`, etc.
            kwargs['type'] = kwargs['type'].__name__
        self.command.option_list +=  (make_option(*args, **kwargs),)


class Command(BaseCommand):
    """
    Queue consumer.  Example usage::

    To start the consumer (note you must export the settings module):

    django-admin.py run_huey
    """
    help = "Run the queue consumer"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        if django.VERSION < (1, 8):
            self.option_list = BaseCommand.option_list
            parser = CompatParser(self)
            self.add_arguments(parser)

    def add_arguments(self, parser):
        parser.add_argument(
            '--workers', '-w',
            dest='workers',
            type=int,
            help='Number of worker threads/processes/greenlets')
        parser.add_argument(
            '--worker-type', '-k',
            dest='worker_type',
            help='worker execution model (thread, greenlet, process).',
            choices=['greenlet', 'thread', 'process', 'gevent'])
        parser.add_argument(
            '--delay', '-d',
            dest='initial_delay',
            type=float,
            help='Delay between polling requests')
        parser.add_argument(
            '--max_delay', '-m',
            dest='max_delay',
            type=float,
            help='Maximum delay between polling requests')
        parser.add_argument(
            '--no-periodic', '-n',
            dest='periodic',
            action='store_false',
            help='Do not enqueue periodic commands')
        parser.add_argument(
            '--verbose', '-V',
            dest='verbose',
            action='store_true',
            help='log debugging statements')
        parser.add_argument(
            '--quiet', '-q',
            dest='verbose',
            action='store_false',
            help='only log exceptions')

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

        consumer_options = {
            'workers': 1,
            'worker_type': 'thread'}

        if isinstance(settings.HUEY, dict):
            consumer_options.update(settings.HUEY.get('consumer', {}))

        for k in ('workers', 'worker_type', 'periodic', 'initial_delay',
                  'max_delay'):
            if options[k] is not None:
                consumer_options[k] = options[k]

        self.autodiscover()

        verbose = None
        if 'verbose' in consumer_options:
            verbose = consumer_options['verbose']
        elif 'quiet' in consumer_options:
            verbose = not consumer_options['quiet']

        loglevel = get_loglevel(verbose)
        logfile = consumer_options.pop('logfile', None)
        setup_logger(loglevel, logfile, consumer_options['worker_type'])

        consumer = Consumer(HUEY, **consumer_options)
        consumer.run()

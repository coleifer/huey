import imp
import sys
from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.importlib import import_module

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
        make_option('--periodic', '-p',
            dest='periodic',
            action='store_true',
            help='Enqueue periodic commands'
        ),
        make_option('--no-periodic', '-n',
            dest='periodic',
            action='store_false',
            help='Do not enqueue periodic commands'
        ),
        make_option('--workers', '-w',
            dest='workers',
            type='int',
            help='Number of worker threads'
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
    )

    def autodiscover(self):
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

    def handle(self, *args, **options):
        from huey.djhuey import HUEY
        try:
            consumer_options = settings.HUEY['consumer_options']
        except:
            consumer_options = {}

        if options['workers'] is not None:
            consumer_options['workers'] = options['workers']

        if options['periodic'] is not None:
            consumer_options['periodic'] = options['periodic']

        if options['initial_delay'] is not None:
            consumer_options['initial_delay'] = options['initial_delay']

        if options['max_delay'] is not None:
            consumer_options['max_delay'] = options['max_delay']

        self.autodiscover()

        loglevel = get_loglevel(consumer_options.pop('loglevel', None))
        logfile = consumer_options.pop('logfile', None)
        setup_logger(loglevel, logfile)

        consumer = Consumer(HUEY, **consumer_options)
        consumer.run()

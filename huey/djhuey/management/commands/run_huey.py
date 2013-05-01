import imp
import sys
from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.importlib import import_module

from huey.bin.huey_consumer import Consumer
from huey.djhuey import huey, config
from huey.utils import load_class


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
        make_option('--threads', '-t',
            dest='threads',
            type='int',
            help='Number of worker threads'
        ),
    )

    def autodiscover(self):
        # this is to find modules named <tasks.py> in a django project's
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
        if options['threads'] is not None:
            config['threads'] = options['threads']

        if options['periodic'] is not None:
            config['periodic'] = options['periodic']

        self.autodiscover()

        consumer = Consumer(huey, **config)
        consumer.run()

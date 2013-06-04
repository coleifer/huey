import imp
import sys
from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.importlib import import_module

from huey.bin.pubsub_consumer import PubSubConsumer


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

        """ PubSubConsumer options should include Redis connection info

            It should look like:
            HUEY = {
                'backend': 'huey.backends.redis_backend',  # required.
                'name': 'unique name',
                'connection': {'host': 'localhost', 'port': 6379},
                'always_eager': False, # Defaults to False when running via manage.py run_huey
                                # Options to pass into the consumer when running ``manage.py run_huey``
                'consumer_options': {
                    'workers': 4,
                    'pubsub':{'host': 'localhost', 'port': 6379, 'channel':'mychannel'},

                },
            }
        """
        from huey.djhuey import HUEY
        try:
            consumer_options = settings.HUEY['consumer_options']
        except:
            consumer_options = {}

        if options['workers'] is not None:
            consumer_options['workers'] = options['workers']

        if options['periodic'] is not None:
            consumer_options['periodic'] = options['periodic']

        self.autodiscover()
        consumer = PubSubConsumer(HUEY, **consumer_options)
        consumer.run()

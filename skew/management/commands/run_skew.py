import imp
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.importlib import import_module

from skew.bin.skew_consumer import Consumer, load_config
from skew.queue import Invoker


class Command(BaseCommand):
    """
    Queue consumer.  Example usage::
    
    To start the consumer (note you must export the settings module):
    
    django-admin.py run_skew
    """
    
    help = "Run the queue consumer"
    option_list = BaseCommand.option_list + (
        make_option('--config', '-f',
            dest='config',
            default=getattr(settings, 'SKEW_CONFIGURATION', ''),
            type='str',
            help='Configuration module, i.e. myproject.config.QueueConfiguration'
        ),
    )
    
    def autodiscover(self):
        # this is to find modules named <commands.py> in a django project's
        # installed apps directories
        module_name = 'commands'
        
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
        config_module = options.get('config')
        if not config_module:
            raise CommandError('No configuration specified.')
        
        config = load_config(config_module)
        
        self.autodiscover()
        
        queue = config.QUEUE
        result_store = config.RESULT_STORE
        invoker = Invoker(queue, result_store)
        
        consumer = Consumer(invoker, config)
        consumer.run()

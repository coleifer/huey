import imp
import logging
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
from huey.consumer_options import ConsumerConfig
from huey.consumer_options import OptionParserHandler


class CompatParser(object):
    """Converts argeparse arguments to optparse for Django < 1.8 compatibility."""

    def __init__(self, command):
        self.command = command

    def add_argument(self, *args, **kwargs):
        if 'type' in kwargs:
            # Convert `type=int` to `type="int"`, etc.
            kwargs['type'] = kwargs['type'].__name__
        self.command.option_list += (make_option(*args, **kwargs),)


class Command(BaseCommand):
    """
    Queue consumer.  Example usage::

    To start the consumer (note you must export the settings module):

    django-admin.py run_huey
    """
    help = "Run the queue consumer"
    _type_map = {'int': int, 'float': float}

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        if django.VERSION < (1, 8):
            self.option_list = BaseCommand.option_list
            parser = CompatParser(self)
            self.add_arguments(parser)

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
                parser.add_argument(full, short, **kwargs)

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

        for key, value in options.items():
            if value is not None:
                consumer_options[key] = value

        consumer_options.setdefault('verbose',
                                    consumer_options.pop('huey_verbose', None))
        self.autodiscover()

        config = ConsumerConfig(**consumer_options)
        config.validate()
        config.setup_logger()

        consumer = Consumer(HUEY, **config.values)
        consumer.run()

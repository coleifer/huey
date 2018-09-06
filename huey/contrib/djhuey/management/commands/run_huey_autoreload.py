"""
    Same as djhuey/management/commands/run_huey.py
    But reload the consumer if files changed
"""
import subprocess
import sys

from django.core.management.base import BaseCommand
from django.utils import autoreload
from django.utils.module_loading import autodiscover_modules


class Command(BaseCommand):
    help = "Run the queue consumer with auto-reload"

    def handle(self, *args, **options):
        autoreload.main(self.inner_run, None, options)

    def inner_run(self, *args, **options):

        # include task.py files to auto-reload trigger
        autodiscover_modules("tasks")

        # Just replace the command name, so you can pass all arguments to run_huey command, e.g.:
        #
        # ./manage.py run_huey_autoreload.py --traceback
        #
        args = sys.argv[:]
        args[1] = "run_huey"

        print("\nStart %r..." % args)

        subprocess.check_call(args)

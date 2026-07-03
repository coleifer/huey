from django.core.management.base import BaseCommand
from django.core.management.base import CommandError


class Command(BaseCommand):
    help = 'Create the tables used by huey\'s SQL storage backends'

    def handle(self, *args, **options):
        from huey.contrib.djhuey import HUEY

        initialize = getattr(HUEY.storage, 'initialize_schema', None)
        if initialize is None:
            raise CommandError('%s storage does not use SQL tables.'
                               % type(HUEY.storage).__name__)

        initialize()
        self.stdout.write('huey tables created.')

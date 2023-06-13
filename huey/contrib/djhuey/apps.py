from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules

from huey.contrib.djhuey import autodiscover


class DjangoHueyAppConfig(AppConfig):
    def ready(self):
        if autodiscover:
            autodiscover_modules("tasks")

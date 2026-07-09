from django.apps import AppConfig


class TestAppConfig(AppConfig):
    name = 'djangoex.test_app'

    def ready(self):
        # Import tasks so they are registered in the web process too - the
        # admin dashboard can only display tasks the current process knows.
        from djangoex.test_app import tasks  # noqa: F401

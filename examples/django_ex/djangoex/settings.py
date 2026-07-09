import logging
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEBUG = True
SECRET_KEY = 'foo'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'huey.contrib.djhuey',
    'huey.contrib.djhuey.stats',
    'djangoex.test_app',
]

MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages']},
}]

HUEY = {
    'name': 'test-django',
    'immediate': False,  # Dict config defaults immediate to DEBUG.
    'consumer': {
        'blocking': True,  # Use blocking list pop instead of polling Redis.
        'loglevel': logging.DEBUG,
        'workers': 4,
        'scheduler_interval': 1,
        'simple_log': True,
    },
}

DATABASES = {'default': {
    'NAME': os.path.join(BASE_DIR, 'djangoex.db'),
    'ENGINE': 'django.db.backends.sqlite3'}}

ROOT_URLCONF = 'djangoex.urls'
STATIC_URL = 'static/'
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

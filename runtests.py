#!/usr/bin/env python
import os
import sys
import unittest

from huey import tests


def _requirements_installed():
    try:
        import django
        return True
    except Exception:
        return False


def run_tests(*test_args):
    suite = unittest.TestLoader().loadTestsFromModule(tests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if result.failures:
        sys.exit(1)
    elif result.errors:
        sys.exit(2)


def run_django_tests(*test_args):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "huey.contrib.djhuey.tests.settings")
    from django.core.management import execute_from_command_line
    args = sys.argv
    args.insert(1, "test")
    execute_from_command_line(args)

if __name__ == '__main__':
    if not _requirements_installed():
        print('Requirements are not installed. Run "pip install -r test_requirements.txt" to install all dependencies.')
        sys.exit(2)
    run_tests(*sys.argv[1:])
    run_django_tests(*sys.argv[1:])
    sys.exit(0)

#!/usr/bin/env python

import glob
import optparse
import os
import sys
import unittest

from huey import tests


def collect_tests(args=None):
    suite = unittest.TestSuite()

    if not args:
        from huey import tests
        module_suite = unittest.TestLoader().loadTestsFromModule(tests)
        suite.addTest(module_suite)
    else:
        tmpl = 'huey.tests.test_%s'
        cleaned = [tmpl % arg if not arg.startswith('test') else arg
                   for arg in args]
        user_suite = unittest.TestLoader().loadTestsFromNames(cleaned)
        suite.addTest(user_suite)
    return suite


def runtests(suite, verbosity=1, failfast=False):
    runner = unittest.TextTestRunner(verbosity=verbosity, failfast=failfast)
    results = runner.run(suite)
    return results.failures, results.errors


if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option('-v', '--verbosity', dest='verbosity', default=1,
                      type='int', help='Verbosity of output')
    parser.add_option('-f', '--failfast', action='store_true', default=False,
                      help='Stop on first failure or error.')

    options, args = parser.parse_args()
    suite = collect_tests(args)
    failures, errors = runtests(suite, options.verbosity, options.failfast)
    for f in glob.glob('huey*.db*'):
        os.unlink(f)

    if errors or failures:
        sys.exit(1)

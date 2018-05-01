#!/usr/bin/env python

import optparse
import os
import sys
import unittest

from huey import tests


def runtests(verbose=False, failfast=False, names=None):
    if names:
        suite = unittest.TestLoader().loadTestsFromNames(names, tests)
    else:
        suite = unittest.TestLoader().loadTestsFromModule(tests)

    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1,
                                     failfast=failfast)
    return runner.run(suite)


if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option('-v', '--verbose', action='store_true', default=False,
                      dest='verbose', help='Verbose output.')
    parser.add_option('-f', '--failfast', action='store_true', default=False,
                      help='Stop on first failure or error.')
    options, args = parser.parse_args()
    result = runtests(
        verbose=options.verbose,
        failfast=options.failfast,
        names=args)

    if os.path.exists('huey.db'):
        os.unlink('huey.db')

    if result.failures:
        sys.exit(1)
    elif result.errors:
        sys.exit(2)

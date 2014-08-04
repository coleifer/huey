#!/usr/bin/env python

import logging
import optparse
import sys
from logging.handlers import RotatingFileHandler

from huey.consumer import Consumer
from huey.utils import load_class


def err(s):
    sys.stderr.write('\033[91m%s\033[0m\n' % s)


def get_loglevel(verbose=None):
    if verbose is None:
        return logging.INFO
    elif verbose:
        return logging.DEBUG
    return logging.ERROR


def setup_logger(loglevel, logfile):
    log_format = ('%(threadName)s %(asctime)s %(name)s '
                  '%(levelname)s %(message)s')
    logging.basicConfig(level=loglevel, format=log_format)

    if logfile:
        handler = RotatingFileHandler(
            logfile, maxBytes=1024*1024, backupCount=3)
        handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(handler)


def get_option_parser():
    parser = optparse.OptionParser(
        'Usage: %prog [options] path.to.huey_instance')
    parser.add_option('-l', '--logfile', dest='logfile',
                      help='write logs to FILE', metavar='FILE')
    parser.add_option('-v', '--verbose', dest='verbose',
                      help='verbose logging', action='store_true')
    parser.add_option('-q', '--quiet', dest='verbose',
                      help='log exceptions only', action='store_false')
    parser.add_option('-w', '--workers', dest='workers', type='int',
                      help='worker threads (default=1)', default=1)
    parser.add_option('-t', '--threads', dest='workers', type='int',
                      help='same as "workers"', default=1)
    parser.add_option('-p', '--periodic', dest='periodic', default=True,
                      help='execute periodic tasks (default=True)',
                      action='store_true')
    parser.add_option('-n', '--no-periodic', dest='periodic',
                      help='do NOT execute periodic tasks',
                      action='store_false')
    parser.add_option('-d', '--delay', dest='initial_delay', type='float',
                      help='initial delay in seconds (default=0.1)',
                      default=0.1)
    parser.add_option('-m', '--max-delay', dest='max_delay', type='float',
                      help='maximum time to wait between polling the queue '
                           '(default=10)',
                      default=10)
    parser.add_option('-b', '--backoff', dest='backoff', type='float',
                      help='amount to backoff delay when no results present '
                           '(default=1.15)',
                      default=1.15)
    parser.add_option('-P', '--periodic-task-interval',
                      dest='periodic_task_interval',
                      type='float', help='Granularity of periodic tasks.',
                      default=60.0)
    parser.add_option('-S', '--scheduler-interval', dest='scheduler_interval',
                      type='float', help='Granularity of scheduler.',
                      default=1.0)
    parser.add_option('-u', '--utc', dest='utc', action='store_true',
                      help='use UTC time for all tasks (default=True)',
                      default=True)
    parser.add_option('--localtime', dest='utc', action='store_false',
                      help='use local time for all tasks')
    return parser


if __name__ == '__main__':
    parser = get_option_parser()
    options, args = parser.parse_args()

    setup_logger(get_loglevel(options.verbose), options.logfile)

    if len(args) == 0:
        err('Error:   missing import path to `Huey` instance')
        err('Example: huey_consumer.py app.queue.huey_instance')
        sys.exit(1)

    try:
        huey_instance = load_class(args[0])
    except:
        err('Error importing %s' % args[0])
        raise

    consumer = Consumer(
        huey_instance,
        options.workers,
        options.periodic,
        options.initial_delay,
        options.backoff,
        options.max_delay,
        options.utc,
        options.scheduler_interval,
        options.periodic_task_interval)
    consumer.run()

#!/usr/bin/env python

import logging
import optparse
import os
import sys
from logging import FileHandler

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


def setup_logger(loglevel, logfile, worker_type):
    if worker_type == 'process':
        worker = '%(process)d'
    else:
        worker = '%(threadName)s'

    log_format = ('[%(asctime)s] %(levelname)s:%(name)s:' + worker +
                  ':%(message)s')
    logging.basicConfig(level=loglevel, format=log_format)

    if logfile:
        handler = FileHandler(logfile)
        handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(handler)


def get_option_parser():
    parser = optparse.OptionParser(
        'Usage: %prog [options] path.to.huey_instance')

    log_opts = parser.add_option_group(
        'Logging',
        'The following options pertain to the logging system.')
    log_opts.add_option('-l', '--logfile',
       dest='logfile',
       help='write logs to FILE',
       metavar='FILE')
    log_opts.add_option('-v', '--verbose',
       action='store_true',
       dest='verbose',
       help='log debugging statements')
    log_opts.add_option('-q', '--quiet',
       action='store_false',
       dest='verbose',
       help='only log exceptions')

    worker_opts = parser.add_option_group(
        'Workers',
        ('By default huey uses a single worker thread. To specify a different '
         'number of workers, or a different execution model (such as multiple '
         'processes or greenlets), use the options below.'))
    worker_opts.add_option('-w', '--workers',
       dest='workers',
       type='int',
       help='number of worker threads/processes (default=1)',
       default=1)
    worker_opts.add_option('-k', '--worker-type',
       dest='worker_type',
       help='worker execution model (thread, greenlet, process).',
       default='thread',
       choices=['greenlet', 'thread', 'process', 'gevent'])
    worker_opts.add_option('-d', '--delay',
       dest='initial_delay',
       type='float',
       help='initial delay between polling intervals in seconds (default=0.1)',
       default=0.1)
    worker_opts.add_option('-m', '--max-delay',
       dest='max_delay',
       type='float',
       help='maximum time to wait between polling the queue (default=10)',
       default=10)
    worker_opts.add_option('-b', '--backoff',
       dest='backoff',
       type='float',
       help='amount to backoff delay when no results present (default=1.15)',
       default=1.15)

    scheduler_opts = parser.add_option_group(
        'Scheduler',
        ('By default Huey will run the scheduler once every second to check '
         'for tasks scheduled in the future, or tasks set to run at specific '
         'intervals (periodic tasks). Use the options below to configure the '
         'scheduler or to disable periodic task scheduling.'))
    scheduler_opts.add_option('-s', '--scheduler-interval',
       dest='scheduler_interval',
       type='int',
       help='Granularity of scheduler in seconds.',
       default=1)
    scheduler_opts.add_option('-n', '--no-periodic',
       action='store_false',
       default=True,
       dest='periodic',
       help='do NOT schedule periodic tasks')
    scheduler_opts.add_option('-u', '--utc',
       dest='utc',
       action='store_true',
       help='use UTC time for all tasks (default=True)',
       default=True)
    scheduler_opts.add_option('--localtime',
       dest='utc',
       action='store_false',
       help='use local time for all tasks')
    return parser


def load_huey(path):
    try:
        return load_class(path)
    except:
        cur_dir = os.getcwd()
        if cur_dir not in sys.path:
            sys.path.insert(0, cur_dir)
            return load_huey(path)
        err('Error importing %s' % path)
        raise


def consumer_main():
    parser = get_option_parser()
    options, args = parser.parse_args()

    setup_logger(
        get_loglevel(options.verbose),
        options.logfile,
        options.worker_type)

    if len(args) == 0:
        err('Error:   missing import path to `Huey` instance')
        err('Example: huey_consumer.py app.queue.huey_instance')
        sys.exit(1)

    if options.workers < 1:
        err('You must have at least one worker.')
        sys.exit(1)

    huey_instance = load_huey(args[0])

    consumer = Consumer(
        huey_instance,
        options.workers,
        options.periodic,
        options.initial_delay,
        options.backoff,
        options.max_delay,
        options.utc,
        options.scheduler_interval,
        options.worker_type)
    consumer.run()


if __name__ == '__main__':
    consumer_main()

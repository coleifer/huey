import logging
import optparse
from collections import namedtuple
from logging import FileHandler

from huey.constants import WORKER_THREAD
from huey.constants import WORKER_TYPES


config_defaults = (
    ('workers', 1),
    ('worker_type', WORKER_THREAD),
    ('initial_delay', 0.1),
    ('backoff', 1.15),
    ('max_delay', 10.0),
    ('check_worker_health', True),
    ('health_check_interval', 10),
    ('scheduler_interval', 1),
    ('periodic', True),
    ('logfile', None),
    ('verbose', None),
    ('simple_log', None),
    ('flush_locks', False),
    ('extra_locks', None),
)
config_keys = [param for param, _ in config_defaults]


def option(name, **options):
    if isinstance(name, tuple):
        letter, opt_name = name
    else:
        opt_name = name.replace('_', '-')
        letter = name[0]
        options.setdefault('dest', name)
    return ('-' + letter, '--' + opt_name, options)


class OptionParserHandler(object):
    def get_worker_options(self):
        return (
            # -w, -k, -d, -m, -b, -c, -C, -f
            option('workers', type='int',
                   help='number of worker threads/processes (default=1)'),
            option(('k', 'worker-type'), choices=WORKER_TYPES,
                   dest='worker_type',
                   help=('worker execution model (thread, greenlet, '
                         'process). Use process for CPU-intensive workloads, '
                         'and greenlet for IO-heavy workloads. When in doubt, '
                         'thread is the safest choice.')),
            option('delay', dest='initial_delay',
                   help='minimum time to wait when polling queue (default=.1)',
                   metavar='SECONDS', type='float'),
            option('max_delay', metavar='SECONDS',
                   help='maximum time to wait when polling queue (default=10)',
                   type='float'),
            option('backoff', metavar='SECONDS',
                   help=('factor used to back-off polling interval when queue '
                         'is empty (default=1.15, must be >= 1)'),
                   type='float'),
            option(('c', 'health-check-interval'), type='float',
                   dest='health_check_interval', metavar='SECONDS',
                   help=('minimum time to wait between worker health checks '
                         '(default=1.0)')),
            option(('C', 'disable-health-check'), action='store_false',
                   dest='check_worker_health',
                   help=('disable health check that monitors worker health, '
                         'restarting any worker that crashes unexpectedly.')),
            option('flush_locks', action='store_true', dest='flush_locks',
                   help=('flush all locks when starting consumer.')),
            option(('L', 'extra-locks'), dest='extra_locks',
                   help=('additional locks to flush, separated by comma.')),
        )

    def get_scheduler_options(self):
        return (
            # -s, -n
            option('scheduler_interval', type='int',
                   help='Granularity of scheduler in seconds.'),
            option('no_periodic', action='store_false',
                   dest='periodic', help='do NOT enqueue periodic tasks'),
        )

    def get_logging_options(self):
        return (
            # -l, -v, -q, -S
            option('logfile', metavar='FILE'),
            option('verbose', action='store_true',
                   help='verbose logging (includes DEBUG statements)'),
            option('quiet', action='store_false', dest='verbose',
                   help='minimal logging'),
            option(('S', 'simple'), action='store_true', dest='simple_log',
                   help='simple logging format (time message)'),
        )

    def get_option_parser(self):
        parser = optparse.OptionParser('Usage: %prog [options] '
                                       'path.to.huey_instance')

        def add_group(name, description, options):
            group = parser.add_option_group(name, description)
            for abbrev, name, kwargs in options:
                group.add_option(abbrev, name, **kwargs)

        add_group('Logging', 'The following options pertain to logging.',
                  self.get_logging_options())

        add_group('Workers', (
            'By default huey uses a single worker thread. To specify a '
            'different number of workers, or a different execution model (such'
            ' as multiple processes or greenlets), use the options below.'),
            self.get_worker_options())

        add_group('Scheduler', (
            'By default Huey will run the scheduler once every second to check'
            ' for tasks scheduled in the future, or tasks set to run at '
            'specfic intervals (periodic tasks). Use the options below to '
            'configure the scheduler or to disable periodic task scheduling.'),
            self.get_scheduler_options())

        return parser


class ConsumerConfig(namedtuple('_ConsumerConfig', config_keys)):
    def __new__(cls, **kwargs):
        config = dict(config_defaults)
        config.update(kwargs)
        args = [config[key] for key in config_keys]
        return super(ConsumerConfig, cls).__new__(cls, *args)

    def validate(self):
        if self.backoff < 1:
            raise ValueError('The backoff must be greater than 1.')
        if not (0 < self.scheduler_interval <= 60):
            raise ValueError('The scheduler must run at least once per '
                             'minute, and at most once per second (1-60).')
        if 60 % self.scheduler_interval != 0:
            raise ValueError('The scheduler interval must be a factor of 60: '
                             '1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, or 60')

    @property
    def loglevel(self):
        if self.verbose is None:
            return logging.INFO
        return logging.DEBUG if self.verbose else logging.WARNING

    def setup_logger(self, logger=None):
        if self.worker_type == 'process':
            worker = '%(process)d'
        else:
            worker = '%(threadName)s'

        if self.simple_log:
            datefmt = '%H:%M:%S'
            logformat = '%(asctime)s %(message)s'
        else:
            datefmt = None  # Use default
            logformat = ('[%(asctime)s] %(levelname)s:%(name)s:' + worker +
                         ':%(message)s')
        if logger is None:
            logger = logging.getLogger()

        if self.logfile:
            handler = logging.FileHandler(self.logfile)
        else:
            handler = logging.StreamHandler()

        handler.setFormatter(logging.Formatter(logformat, datefmt))
        logger.addHandler(handler)
        logger.setLevel(self.loglevel)

    @property
    def values(self):
        return dict((key, getattr(self, key)) for key in config_keys
                    if key not in ('logfile', 'verbose', 'simple_log'))

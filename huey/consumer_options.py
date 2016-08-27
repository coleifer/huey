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
    ('health_check_interval', 1),
    ('scheduler_interval', 1),
    ('periodic', True),
    ('utc', True),
    ('logfile', None),
    ('verbose', None),
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
            # -w, -k, -d, -m, -b, -c, -C
            option('workers', default=1, type='int',
                   help='number of worker threads/processes (default=1)'),
            option(('k', 'worker-type'), choices=WORKER_TYPES,
                   default=WORKER_THREAD, dest='worker_type',
                   help=('worker execution model (thread, greenlet, '
                         'process). Use process for CPU-intensive workloads, '
                         'and greenlet for IO-heavy workloads. When in doubt, '
                         'thread is the safest choice.')),
            option('delay', default=0.1, dest='initial_delay',
                   help='minimum time to wait when polling queue (default=.1)',
                   metavar='SECONDS', type='float'),
            option('max_delay', default=10, metavar='SECONDS',
                   help='maximum time to wait when polling queue (default=10)',
                   type='float'),
            option('backoff', default=1.15, metavar='SECONDS',
                   help=('factor used to back-off polling interval when queue '
                         'is empty (default=1.15, must be >= 1)'),
                   type='float'),
            option(('c', 'health_check_interval'), default=1.0, type='float',
                   dest='health_check_interval', metavar='SECONDS',
                   help=('minimum time to wait between worker health checks '
                         '(default=1.0)')),
            option(('C', 'disable_health_check'), action='store_false',
                   default=True, dest='check_worker_health',
                   help=('disable health check that monitors worker health, '
                         'restarting any worker that crashes unexpectedly.')),

        )

    def get_scheduler_options(self):
        return (
            # -s, -n, -u, -o
            option('scheduler_interval', default=1, type='int',
                   help='Granularity of scheduler in seconds.'),
            option('no_periodic', action='store_false', default=True,
                   dest='periodic', help='do NOT enqueue periodic tasks'),
            option('utc', action='store_true', default=True,
                   help='use UTC time for all tasks (default=True)'),
            option(('o', 'localtime'), action='store_false', dest='utc',
                   help='use local time for all tasks'),
        )

    def get_logging_options(self):
        return (
            # -l, -v, -q
            option('logfile', metavar='FILE'),
            option('verbose', action='store_true',
                   help='verbose logging (includes DEBUG statements)'),
            option('quiet', action='store_false', dest='verbose',
                   help='minimal logging (only exceptions/errors)'),
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

    @property
    def loglevel(self):
        if self.verbose is None:
            return logging.INFO
        return logging.DEBUG if self.verbose else logging.ERROR

    def setup_logger(self, logger=None):
        if self.worker_type == 'process':
            worker = '%(process)d'
        else:
            worker = '%(threadName)s'

        logformat = ('[%(asctime)s] %(levelname)s:%(name)s:' + worker +
                     ':%(message)s')
        loglevel = self.loglevel
        if logger is None:
            logging.basicConfig(level=loglevel, format=logformat)
            logger = logging.getLogger()
        else:
            logger.setLevel(loglevel)

        if self.logfile:
            handler = FileHandler(self.logfile)
            handler.setFormatter(logging.Formatter(logformat))
            logger.addHandler(handler)

    @property
    def values(self):
        return dict((key, getattr(self, key)) for key in config_keys
                    if key not in ('logfile', 'verbose'))

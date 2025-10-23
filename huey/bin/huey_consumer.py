#!/usr/bin/env python

import logging
import os
import sys

from huey.constants import WORKER_PROCESS
from huey.consumer import Consumer
from huey.consumer_options import ConsumerConfig
from huey.consumer_options import OptionParserHandler
from huey.utils import load_class


def err(s):
    sys.stderr.write('\033[91m%s\033[0m\n' % s)


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
    parser_handler = OptionParserHandler()
    parser = parser_handler.get_option_parser()
    options, args = parser.parse_args()

    if len(args) == 0:
        err('Error:   missing import path to `Huey` instance')
        err('Example: huey_consumer.py app.queue.huey_instance')
        sys.exit(1)

    options = {k: v for k, v in options.__dict__.items()
               if v is not None}
    config = ConsumerConfig(**options)
    config.validate()

    if sys.platform == 'win32' and config.worker_type == WORKER_PROCESS:
        err('Error:  huey cannot be run in "process"-mode on Windows.')
        sys.exit(1)

    huey_instance = load_huey(args[0])

    # Set up logging for the "huey" namespace.
    logger = logging.getLogger('huey')
    config.setup_logger(logger)

    consumer = huey_instance.create_consumer(**config.values)
    consumer.run()


if __name__ == '__main__':
    # MacOS on 3.8+ and Linux on 3.14+ need to explicitly specify forking.
    if ((sys.version_info >= (3, 8) and sys.platform == 'darwin') or
        (sys.version_info >= (3, 14))):
        import multiprocessing
        try:
            multiprocessing.set_start_method('fork')
        except RuntimeError:
            pass
    consumer_main()

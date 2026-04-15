#!/usr/bin/env python

import logging
import os
import sys
import multiprocessing

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
    except Exception:
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
    huey_instance = load_huey(args[0])

    logger = logging.getLogger('huey')
    config.setup_logger(logger)
    os.environ['HUEY_LOGLEVEL'] = str(logger.level)
    
    # It is injected into the configuration so that the Consumer passes it on to 
    # the child processes in Windows ("spawn") and they can rebuild the instance.
    if args:
        config.values['huey_import_path'] = args[0]

    consumer = huey_instance.create_consumer(**config.values)
    consumer.run()

if __name__ == '__main__':
    # We explicitly set 'fork' on platforms that support it. 
    # On Windows, 'fork' is not available so we skip this
    # entirely — Windows always uses 'spawn' by default.
    if sys.platform != 'win32':
        try:
            if 'fork' in multiprocessing.get_all_start_methods():
                multiprocessing.set_start_method('fork')
        except (ValueError, RuntimeError):
            pass

    consumer_main()

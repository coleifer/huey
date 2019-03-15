#!/usr/bin/env python

import os
import sys

from h2.consumer import Consumer
from h2.consumer_options import ConsumerConfig
from h2.consumer_options import OptionParserHandler
from h2.utils import load_class


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

    huey_instance = load_huey(args[0])
    config.setup_logger()

    consumer = huey_instance.create_consumer(**config.values)
    consumer.run()


if __name__ == '__main__':
    consumer_main()

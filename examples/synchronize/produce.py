#!/usr/bin/env python

import logging
from consume import search_yahoo, search_google


def run():
    # Generate 10 search terms
    terms = ['test%s' % (i + 1) for i in range(0, 10)]

    # Call the yahoo queue_command and synchronously resolve the results
    tasks = [search_yahoo(t) for t in terms]
    resolve(tasks, prefix='search_yahoo')

    # Call the google queue_command and synchronously resolve the results
    tasks = [search_google(t) for t in terms]
    resolve(tasks, prefix='search_google')


def resolve(tasks, prefix=None):
    if prefix:
        prefix = prefix.strip()

    if prefix:
        prefix = '%s - ' % prefix

    for task in tasks:
        logging.debug('enqueued task - %s%s', prefix, task.command.task_id)

    for task in tasks:
        logging.debug('resolving task - %s%s', prefix, task.command.task_id)
        task.get(blocking=True, timeout=30)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    try:
        run()
    except KeyboardInterrupt:
        pass

from functools import wraps

from huey import RedisHuey


def _task_wrapper(task_fn, pre_task=None, post_task=None):
    @wraps(task_fn)
    def inner(*args, **kwargs):
        if pre_task is not None:
            pre_task()
        result = task_fn(*args, **kwargs)
        if post_task is not None:
            post_task()
        return result
    return inner


class RedisHueyExt(RedisHuey):
    def task(self, pre_task=None, post_task=None, *args, **kwargs):
        def decorator(fn):
            return (super(RedisHueyExt, self)
                    .task(*args, **kwargs)(_task_wrapper(
                        fn,
                        pre_task=pre_task,
                        post_task=post_task)))
        return decorator

    def periodic_task(self, pre_task=None, post_task=None, *args, **kwargs):
        def decorator(fn):
            return (super(RedisHueyExt, self)
                    .periodic_task(*args, **kwargs)(_task_wrapper(
                        fn,
                        pre_task=pre_task,
                        post_task=post_task)))
        return decorator

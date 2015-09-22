from functools import wraps


def _transaction(db, fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        # Execute function in its own connection, in a transaction.
        with db.execution_context(with_transaction=True):
            return fn(*args, **kwargs)
    return inner

def db_task(huey, db, *args, **kwargs):
    def decorator(fn):
        return huey.task(*args, **kwargs)(_transaction(db, fn))
    return decorator

def db_periodic_task(huey, db, *args, **kwargs):
    def decorator(fn):
        return huey.periodic_task(*args, **kwargs)(_transaction(db, fn))
    return decorator

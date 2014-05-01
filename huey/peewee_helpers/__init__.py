from functools import wraps


def _transaction(db, fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        db.get_conn()
        try:
            with db.transaction():
                return fn(*args, **kwargs)
        finally:
            db.close()
    return inner

def db_task(huey, db, *args, **kwargs):
    def decorator(fn):
        return huey.task(*args, **kwargs)(_transaction(db, fn))
    return decorator

def db_periodic_task(huey, db, *args, **kwargs):
    def decorator(fn):
        return huey.periodic_task(*args, **kwargs)(_transaction(db, fn))
    return decorator

from huey.contrib.flask_admin.stats import HueyStats
from huey.contrib.flask_admin.stats import enable_huey_admin

try:
    import flask_peewee  # noqa: F401
except ImportError:
    # The recorder (enable_huey_admin/HueyStats) needs only peewee, so the
    # consumer can import and install it without flask/flask-peewee.
    HueyPanel = None
else:
    from huey.contrib.flask_admin.panel import HueyPanel


__all__ = ['HueyPanel', 'HueyStats', 'enable_huey_admin']

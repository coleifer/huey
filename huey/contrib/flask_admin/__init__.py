from huey.contrib.stats import HueyStats
from huey.contrib.stats import enable_stats

try:
    import flask_peewee  # noqa: F401
except ImportError:
    HueyPanel = None
else:
    from huey.contrib.flask_admin.panel import HueyPanel


__all__ = ['HueyPanel', 'HueyStats', 'enable_stats']

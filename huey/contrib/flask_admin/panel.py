import os

from flask import redirect, render_template, request, url_for
from jinja2 import ChoiceLoader, FileSystemLoader

from flask_peewee.admin import AdminPanel

from huey.contrib.stats import enable_stats


TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')


class HueyPanel(AdminPanel):
    template_name = 'admin/huey/card.html'
    list_limit = 50
    event_limit = 50
    throughput_minutes = 60

    def __init__(self, admin, title, huey, db=None, **kwargs):
        super(HueyPanel, self).__init__(admin, title)
        db = db or getattr(getattr(admin, 'auth', None), 'db', None)
        if db is None:
            raise RuntimeError('No database available for huey stats; pass one '
                               'explicitly: '
                               'admin.register_panel("Huey", HueyPanel, huey, db)')
        self.huey = huey
        self.stats = enable_stats(self.huey, db, **kwargs)
        self._install_templates(admin.app)

    def _install_templates(self, app):
        env = app.jinja_env
        if getattr(env, '_huey_admin', False):
            return
        env.loader = ChoiceLoader([env.loader, FileSystemLoader(TEMPLATE_DIR)])
        env._huey_admin = True

    def detail_url(self):
        return url_for(self.get_url_name('index'))

    def _live(self):
        data = {}
        for key, method in (('pending', self.huey.pending_count),
                            ('scheduled', self.huey.scheduled_count),
                            ('results', self.huey.result_count)):
            try:
                data[key] = method()
            except Exception:
                data[key] = None
        return data

    def _pending(self):
        try:
            return [{'task': type(t).__name__, 'id': t.id,
                     'priority': t.priority, 'eta': t.eta}
                    for t in self.huey.pending(self.list_limit)]
        except Exception:
            return []

    def _scheduled(self):
        try:
            return [{'task': type(t).__name__, 'id': t.id, 'eta': t.eta}
                    for t in self.huey.scheduled(self.list_limit)]
        except Exception:
            return []

    def _known_tasks(self):
        out = []
        for full, task_class in sorted(self.huey._registry._registry.items()):
            try:
                revoked = self.huey.is_revoked(task_class)
            except Exception:
                revoked = False
            out.append({'full': full, 'task': task_class.__name__,
                        'revoked': revoked})
        return out

    def _overview(self):
        window = self.stats.window_counts()
        completed = window.get('complete', 0)
        errors = window.get('error', 0)
        total = completed + errors
        return {'completed': completed, 'errors': errors,
                'retries': window.get('retrying', 0),
                'error_rate': (errors / total) if total else 0,
                'inflight': len(self.stats.inflight())}

    def get_context(self):
        context = {'live': self._live(), 'detail_url': self.detail_url(),
                   'enabled': True, 'overview': None, 'spark': []}
        try:
            context['overview'] = self._overview()
            context['spark'] = self.stats.throughput(30)['complete']
        except Exception:
            context['enabled'] = False
        return context

    def get_urls(self):
        return (
            ('/', self.index),
            ('/fragment', self.fragment),
            ('/action', self.action),
        )

    def _context(self):
        breakdown = self.stats.task_breakdown()
        return dict(
            panel=self, live=self._live(), overview=self._overview(),
            stats_map={row['full']: row for row in breakdown},
            inflight=self.stats.inflight(),
            events=self.stats.recent_events(self.event_limit),
            pending=self._pending(), scheduled=self._scheduled(),
            known=self._known_tasks(),
            throughput=self.stats.throughput(self.throughput_minutes))

    def index(self):
        return render_template('admin/huey/dashboard.html', admin=self.admin,
                               **self._context())

    def fragment(self):
        return render_template('admin/huey/_content.html', **self._context())

    def action(self):
        op = request.form.get('op')
        huey = self.huey
        try:
            if op == 'revoke_task':
                huey.revoke_all(huey._registry.string_to_task(
                    request.form['task']))
            elif op == 'restore_task':
                huey.restore_all(huey._registry.string_to_task(
                    request.form['task']))
            elif op == 'revoke_id':
                huey.revoke_by_id(request.form['id'])
            elif op == 'restore_id':
                huey.restore_by_id(request.form['id'])
            elif op == 'flush_queue':
                huey.storage.flush_queue()
            elif op == 'flush_results':
                huey.storage.flush_results()
            elif op == 'flush_schedule':
                huey.storage.flush_schedule()
            elif op == 'flush_locks':
                huey.flush_locks()
        except Exception:
            pass
        return redirect(self.detail_url())

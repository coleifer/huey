import os

from flask import redirect, render_template, request, url_for
from jinja2 import ChoiceLoader, FileSystemLoader

from flask_peewee.admin import AdminPanel

from huey.contrib.stats import dashboard_context
from huey.contrib.stats import enable_stats
from huey.contrib.stats import live_counts


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

    def get_context(self):
        context = {'live': live_counts(self.huey),
                   'detail_url': self.detail_url(),
                   'enabled': True, 'overview': None, 'spark': []}
        try:
            context['overview'] = self.stats.overview()
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
        context = dashboard_context(self.huey, self.stats, self.list_limit,
                                    self.event_limit, self.throughput_minutes)
        context['panel'] = self
        return context

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

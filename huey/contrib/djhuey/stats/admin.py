from urllib.parse import urlencode

from django.contrib import admin
from django.contrib.auth import get_permission_codename
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse

from huey.contrib.djhuey.stats.models import HueyDashboard


def get_huey():
    from huey.contrib.djhuey import HUEY
    return HUEY


@admin.register(HueyDashboard)
class HueyDashboardAdmin(admin.ModelAdmin):
    list_limit = 50
    event_limit = 50
    event_page_size = 100
    throughput_minutes = 60

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_action_permission(self, request):
        codename = get_permission_codename('change', self.opts)
        return request.user.has_perm('%s.%s' % (self.opts.app_label, codename))

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path('fragment/', wrap(self.fragment_view),
                 name='hueystats_dashboard_fragment'),
            path('action/', wrap(self.action_view),
                 name='hueystats_dashboard_action'),
            path('events/', wrap(self.events_view),
                 name='hueystats_dashboard_events'),
        ] + super().get_urls()

    def _context(self, request):
        from huey.contrib.stats import dashboard_context
        from huey.contrib.stats import live_counts
        huey = get_huey()
        stats = getattr(huey, '_stats', None)
        can_act = self.has_action_permission(request)
        if stats is None:
            return {'enabled': False, 'live': live_counts(huey),
                    'can_act': can_act}
        context = dashboard_context(huey, stats, self.list_limit,
                                    self.event_limit, self.throughput_minutes)
        context['enabled'] = True
        context['can_act'] = can_act
        for row in context['known']:
            if row['stats'] is None:
                row['stats'] = {'executed': 0, 'completed': 0, 'errors': 0,
                                'retries': 0, 'avg': None}
        context['danger_ops'] = [
            ('flush_queue', 'Flush queue'),
            ('flush_schedule', 'Flush schedule'),
            ('flush_results', 'Flush results'),
            ('flush_locks', 'Flush locks')]
        live, o = context['live'], context['overview']
        context['tiles'] = [
            {'value': live['pending'], 'label': 'Pending', 'cls': ''},
            {'value': live['scheduled'], 'label': 'Scheduled', 'cls': ''},
            {'value': live['results'], 'label': 'Results', 'cls': ''},
            {'value': o['inflight'], 'label': 'Running', 'cls': 'hs-run'},
            {'value': o['completed'], 'label': 'Completed 24h',
             'cls': 'hs-ok'},
            {'value': o['errors'], 'label': 'Errors 24h', 'cls': 'hs-err',
             'sub': '%.1f%% error rate' % (o['error_rate'] * 100)},
        ]
        return context

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        context = {**self.admin_site.each_context(request), 'title': 'Huey',
                   **self._context(request)}
        return TemplateResponse(request, 'admin/hueystats/dashboard.html',
                                context)

    def fragment_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        return TemplateResponse(request, 'admin/hueystats/_content.html',
                                self._context(request))

    def events_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        stats = getattr(get_huey(), '_stats', None)
        context = {**self.admin_site.each_context(request),
                   'title': 'Huey events', 'enabled': stats is not None}
        if stats is not None:
            signal = request.GET.get('signal') or ''
            task = request.GET.get('task') or ''
            q = request.GET.get('q') or ''
            try:
                page = max(0, int(request.GET.get('p', 0)))
            except (TypeError, ValueError):
                page = 0
            n = self.event_page_size
            total, events = stats.search_events(
                signal=signal or None, task=task or None, q=q or None,
                limit=n, offset=page * n)
            qs = urlencode([(k, v) for k, v in (
                ('signal', signal), ('task', task), ('q', q)) if v])
            context.update(
                events=events, total=total, page=page, signal=signal,
                task=task, q=q, signals=stats.event_signals(),
                tasks=stats.event_tasks(), qs=qs + '&' if qs else '',
                prev_page=page - 1, next_page=page + 1,
                has_next=(page + 1) * n < total,
                start=page * n + 1, end=min(total, page * n + len(events)))
        return TemplateResponse(request, 'admin/hueystats/events.html',
                                context)

    def action_view(self, request):
        if not self.has_action_permission(request) or request.method != 'POST':
            raise PermissionDenied
        from huey.contrib.stats import run_action
        run_action(get_huey(), request.POST.get('op'), request.POST)
        return HttpResponseRedirect(
            reverse('admin:hueystats_hueydashboard_changelist'))

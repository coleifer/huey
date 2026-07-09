import time

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse

from huey.contrib.djhuey.stats.models import HueyDashboard
from huey.contrib.djhuey.stats.models import HueyEvent
from huey.contrib.djhuey.stats.templatetags.hueystats import fmt_duration


def get_huey():
    from huey.contrib.djhuey import HUEY
    return HUEY


@admin.register(HueyEvent)
class HueyEventAdmin(admin.ModelAdmin):
    list_display = ('event_time', 'queue', 'task', 'signal',
                    'event_duration', 'error')
    list_filter = ('signal', 'queue', 'task')
    search_fields = ('task_id', 'task', 'error')
    ordering = ('-id',)
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def event_time(self, obj):
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(obj.ts))
    event_time.short_description = 'time'
    event_time.admin_order_field = 'ts'

    def event_duration(self, obj):
        return fmt_duration(obj.duration)
    event_duration.short_description = 'duration'
    event_duration.admin_order_field = 'duration'


@admin.register(HueyDashboard)
class HueyDashboardAdmin(admin.ModelAdmin):
    list_limit = 50
    event_limit = 50
    throughput_minutes = 60

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path('fragment/', wrap(self.fragment_view),
                 name='hueystats_dashboard_fragment'),
            path('action/', wrap(self.action_view),
                 name='hueystats_dashboard_action'),
        ] + super().get_urls()

    def _context(self, request):
        from huey.contrib.stats import dashboard_context
        from huey.contrib.stats import live_counts
        huey = get_huey()
        stats = getattr(huey, '_stats', None)
        if stats is None:
            return {'enabled': False, 'live': live_counts(huey)}
        context = dashboard_context(huey, stats, self.list_limit,
                                    self.event_limit, self.throughput_minutes)
        context['enabled'] = True
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

    def action_view(self, request):
        if not self.has_view_permission(request) or request.method != 'POST':
            raise PermissionDenied
        huey = get_huey()
        op = request.POST.get('op')
        try:
            if op == 'revoke_task':
                huey.revoke_all(huey._registry.string_to_task(
                    request.POST['task']))
            elif op == 'restore_task':
                huey.restore_all(huey._registry.string_to_task(
                    request.POST['task']))
            elif op == 'revoke_id':
                huey.revoke_by_id(request.POST['id'])
            elif op == 'restore_id':
                huey.restore_by_id(request.POST['id'])
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
        return HttpResponseRedirect(
            reverse('admin:hueystats_hueydashboard_changelist'))

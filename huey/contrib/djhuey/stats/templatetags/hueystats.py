from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe


register = template.Library()

SIGNAL_CLASSES = {
    'complete': 'ok', 'error': 'err', 'executing': 'run',
    'retrying': 'warn', 'timeout': 'warn', 'expired': 'warn',
    'interrupted': 'warn', 'scheduled': 'info', 'revoked': 'dark',
    'canceled': 'dark'}


def fmt_duration(seconds):
    if seconds is None:
        return ''
    elif seconds < 1:
        return '%d ms' % (seconds * 1000)
    return '%.2f s' % seconds


@register.filter
def dur(seconds):
    return fmt_duration(seconds) or mark_safe('&mdash;')


@register.filter
def elapsed(seconds):
    if seconds < 60:
        return '%.1fs' % seconds
    elif seconds < 3600:
        return '%dm %ds' % (seconds // 60, seconds % 60)
    return '%dh %dm' % (seconds // 3600, (seconds % 3600) // 60)


@register.simple_tag
def sigbadge(signal):
    cls = SIGNAL_CLASSES.get(signal, 'quiet')
    return format_html('<span class="hs-badge hs-sig-{}">{}</span>',
                       cls, signal)


@register.simple_tag
def barchart(complete, error, w=600, h=56):
    n = len(complete) or 1
    error = error or ([0] * n)
    bw = w / n
    pad = 4
    base = h - pad
    ph = base - pad
    mx = max([1] + [c + e for c, e in zip(complete, error)])
    parts = ['<svg class="hs-barchart" viewBox="0 0 %s %s" '
             'preserveAspectRatio="none">' % (w, h),
             '<rect x="0" y="%s" width="%s" height="%s" fill="currentColor" '
             'opacity="0.035"></rect>' % (pad, w, ph)]
    for gx in (n // 4, n // 2, 3 * n // 4):
        parts.append('<line x1="%.1f" y1="%s" x2="%.1f" y2="%s" '
                     'stroke="currentColor" opacity="0.09" '
                     'vector-effect="non-scaling-stroke"></line>'
                     % (gx * bw, pad, gx * bw, base))
    for i, (c, e) in enumerate(zip(complete, error)):
        x = i * bw + bw * 0.15
        bwid = bw * 0.7
        hc = (c / mx) * ph
        he = (e / mx) * ph
        if c:
            parts.append('<rect x="%.2f" y="%.2f" width="%.2f" '
                         'height="%.2f" class="hs-bar-ok"></rect>'
                         % (x, base - hc, bwid, hc))
        if e:
            parts.append('<rect x="%.2f" y="%.2f" width="%.2f" '
                         'height="%.2f" class="hs-bar-err"></rect>'
                         % (x, base - hc - he, bwid, he))
    parts.append('<line x1="0" y1="%s" x2="%s" y2="%s" '
                 'stroke="currentColor" opacity="0.25" '
                 'vector-effect="non-scaling-stroke"></line></svg>'
                 % (base, w, base))
    return mark_safe(''.join(parts))

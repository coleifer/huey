import datetime
import re

from functools import wraps

from huey.queue import QueueCommand, PeriodicQueueCommand
from huey.utils import local_to_utc


def create_command(command_class, func, **kwargs):
    def execute(self):
        args, kwargs = self.data or ((), {})
        return func(*args, **kwargs)
    
    attrs = {
        'execute': execute,
        '__module__': func.__module__,
        '__doc__': func.__doc__
    }
    attrs.update(kwargs)
    
    klass = type(
        'queuecmd_%s' % (func.__name__),
        (command_class,),
        attrs
    )
    
    return klass

def queue_command(invoker, retries=0):
    def decorator(func):
        """
        Decorator to execute a function out-of-band via the consumer.  Usage::
        
        @queue_command(invoker)
        def send_email(user, message):
            ... this code executed when dequeued by the consumer ...
        """
        klass = create_command(QueueCommand, func)
        
        def schedule(args=None, kwargs=None, eta=None, convert_utc=True):
            if convert_utc and eta:
                eta = local_to_utc(eta)
            cmd = klass((args or (), kwargs or {}), execute_time=eta, retries=retries)
            return invoker.enqueue(cmd)
        
        func.schedule = schedule
        
        @wraps(func)
        def inner_run(*args, **kwargs):
            return invoker.enqueue(klass((args, kwargs), retries=retries))
        return inner_run
    return decorator

def periodic_command(invoker, validate_datetime):
    """
    Decorator to execute a function on a specific schedule.  This is a bit
    different than :func:queue_command in that it does *not* cause items to
    be enqueued when called, but rather causes a PeriodicQueueCommand to be
    registered with the global invoker.
    
    A note on usage:
    
        Since the command is called at a given schedule, it cannot be "triggered"
        by a run-time event.  As such, there should never be any need for 
        parameters, since nothing can vary between executions
    """
    def decorator(func):
        def method_validate(self, dt):
            return validate_datetime(dt)
        
        klass = create_command(
            PeriodicQueueCommand,
            func,
            validate_datetime=method_validate
        )
        
        return func
    return decorator


dash_re = re.compile('(\d+)-(\d+)')
every_re = re.compile('\*\/(\d+)')

def crontab(month='*', day='*', day_of_week='*', hour='*', minute='*'):
    """
    Convert a "crontab"-style set of parameters into a test function that will
    return True when the given datetime matches the parameters set forth in
    the crontab.
    
    Acceptable inputs:
    * = every distinct value
    */n = run every "n" times, i.e. hours='*/4' == 0, 4, 8, 12, 16, 20
    m-n = run every time m..n
    m,n = run on m and n
    """
    validation = (
        ('m', month, range(1, 13)),
        ('d', day, range(1, 32)),
        ('w', day_of_week, range(7)),
        ('H', hour, range(24)),
        ('M', minute, range(60))
    )
    cron_settings = []
    min_interval = None
    
    for (date_str, value, acceptable) in validation:
        settings = set([])
        
        if isinstance(value, int):
            value = str(value)
        
        for piece in value.split(','):
            if piece == '*':
                settings.update(acceptable)
                continue
            
            if piece.isdigit():
                piece = int(piece)
                if piece not in acceptable:
                    raise ValidationError('%d is not a valid input' % piece)
                settings.add(piece)
            
            else:
                dash_match = dash_re.match(piece)
                if dash_match:
                    lhs, rhs = map(int, dash_match.groups())
                    if lhs not in acceptable or rhs not in acceptable:
                        raise ValidationError('%s is not a valid input' % piece)
                    settings.update(range(lhs, rhs+1))
                    continue
                
                every_match = every_re.match(piece)
                if every_match:
                    interval = int(every_match.groups()[0])
                    settings.update(acceptable[::interval])
        
        cron_settings.append(sorted(list(settings)))
    
    def validate_date(dt):
        _, m, d, H, M, _, w, _, _ = dt.timetuple()
        
        # fix the weekday to be sunday=0
        w = (w + 1) % 7
        
        for (date_piece, selection) in zip([m, d, w, H, M], cron_settings):
            if date_piece not in selection:
                return False
        
        return True
    
    return validate_date

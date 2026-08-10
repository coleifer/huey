import atexit
import os
import threading
import time

import peewee

from huey import signals as S


TERMINAL = frozenset((
    S.SIGNAL_COMPLETE, S.SIGNAL_ERROR, S.SIGNAL_CANCELED, S.SIGNAL_INTERRUPTED,
    S.SIGNAL_EXPIRED, S.SIGNAL_REVOKED))

database = peewee.DatabaseProxy()


class BaseModel(peewee.Model):
    class Meta:
        database = database


class HueyEvent(BaseModel):
    ts = peewee.DoubleField(index=True)
    queue = peewee.CharField(index=True)
    task_id = peewee.CharField()
    task = peewee.CharField(index=True)
    signal = peewee.CharField()
    duration = peewee.DoubleField(null=True)
    error = peewee.TextField(null=True)
    args = peewee.TextField(null=True)

    class Meta:
        table_name = 'huey_event'


class HueyInflight(BaseModel):
    task_id = peewee.CharField(primary_key=True)
    queue = peewee.CharField(index=True)
    task = peewee.CharField()
    started = peewee.DoubleField()

    class Meta:
        table_name = 'huey_inflight'


MODELS = (HueyEvent, HueyInflight)


def _resolve_db(db):
    if isinstance(db, peewee.Database):
        return db
    inner = getattr(db, 'database', None)  # flask_peewee.db.Database wrapper.
    if isinstance(inner, peewee.Database):
        return inner
    raise TypeError('Expected a peewee Database or flask_peewee Database, got '
                    '%r' % (db,))


class HueyStats(object):
    def __init__(self, huey, db, retention_hours=48, max_events=2000,
                 capture_args=False, create_tables=True, flush_interval=0.5,
                 flush_max=200):
        self.huey = huey
        self.name = huey.name
        self.db = _resolve_db(db)
        self.retention = retention_hours * 3600
        self.max_events = max_events
        self.capture_args = capture_args
        self._flush_interval = flush_interval
        self._flush_max = flush_max

        self._buf = []
        self._start = {}
        self._lock = threading.Lock()
        self._writer = None
        self._connected = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._prune_at = 0

        if database.obj is None:
            database.initialize(self.db)
        if create_tables:
            # The writer thread opens its own connection. Close the one
            # create_tables opens, so forked children do not inherit a live
            # socket. Leave a connection the caller opened alone.
            was_closed = self.db.is_closed()
            self.db.create_tables(MODELS, safe=True)
            if was_closed:
                self.db.close()

    def connect(self):
        if self._connected:
            return
        self._connected = True
        self.huey.signal()(self._on_signal)
        # Worker processes exit via os._exit, which skips atexit-based flush.
        self.huey.on_shutdown('huey_stats_flush')(self._flush)
        if hasattr(os, 'register_at_fork'):
            os.register_at_fork(after_in_child=self._reset_after_fork)
        self._start_writer()
        atexit.register(self.close)

    def _start_writer(self):
        self._writer = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer.start()

    def _reset_after_fork(self):
        # Runs in the forked child while it is still single-threaded. The
        # writer thread exists only in the parent, along with any locks it
        # held at fork time. Rows buffered before the fork are the parent's
        # to write. The inherited db connection shares a socket with the
        # parent, so discard its state rather than close it.
        if self._stop.is_set():
            return
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._buf = []
        self._start = {}
        self.db._state.reset()
        self._start_writer()

    def _on_signal(self, signal, task, exc=None):
        try:
            now = time.time()
            t = type(task)
            duration = None
            if signal == S.SIGNAL_EXECUTING:
                self._start[task.id] = now
            elif signal in TERMINAL:
                started = self._start.pop(task.id, None)
                if started is not None:
                    duration = now - started
            row = {
                'ts': now, 'queue': self.name, 'task_id': str(task.id),
                'task': '%s.%s' % (t.__module__, t.__name__), 'signal': signal,
                'duration': duration,
                'error': repr(exc)[:1000] if (signal == S.SIGNAL_ERROR and exc)
                    else None,
                'args': ('%r %r' % (task.args, task.kwargs))[:400]
                    if self.capture_args else None}
            with self._lock:
                self._buf.append(row)
                pending = len(self._buf)
            if pending >= self._flush_max:
                self._wake.set()
        except Exception:
            pass

    def _writer_loop(self):
        while not self._stop.is_set():
            self._wake.wait(self._flush_interval)
            self._wake.clear()
            self._flush()
        if not self.db.is_closed():
            self.db.close()

    def _flush(self):
        with self._lock:
            batch = self._buf
            self._buf = []
        if not batch:
            return
        # One inflight op per task, applied in task_id order, so concurrent
        # writers acquire row locks identically and cannot deadlock.
        inflight = {}
        for row in batch:
            if row['signal'] == S.SIGNAL_EXECUTING:
                inflight[row['task_id']] = row
            elif row['signal'] in TERMINAL:
                inflight[row['task_id']] = None
        try:
            with self.db.atomic():
                HueyEvent.insert_many(batch).execute()
                for task_id in sorted(inflight):
                    row = inflight[task_id]
                    HueyInflight.delete().where(
                        HueyInflight.task_id == task_id).execute()
                    if row is not None:
                        HueyInflight.insert(
                            task_id=task_id, queue=row['queue'],
                            task=row['task'], started=row['ts']).execute()
        except Exception:
            return
        self._maybe_prune()

    def _maybe_prune(self):
        now = time.time()
        if now < self._prune_at:
            return
        self._prune_at = now + 60
        try:
            with self.db.atomic():
                (HueyEvent.delete()
                 .where(HueyEvent.queue == self.name,
                        HueyEvent.ts < now - self.retention).execute())
                mx = (HueyEvent.select(peewee.fn.MAX(HueyEvent.id))
                      .where(HueyEvent.queue == self.name).scalar())
                if mx:
                    (HueyEvent.delete()
                     .where(HueyEvent.queue == self.name,
                            HueyEvent.id < mx - self.max_events).execute())
                (HueyInflight.delete()
                 .where(HueyInflight.queue == self.name,
                        HueyInflight.started < now - 21600).execute())
        except Exception:
            pass
        if len(self._start) > 10000:
            self._start.clear()

    def close(self):
        if self._stop.is_set():
            return
        self._stop.set()
        self._wake.set()
        if self._writer is not None:
            self._writer.join(timeout=2)

    def _events(self):
        return HueyEvent.select().where(HueyEvent.queue == self.name)

    def window_counts(self, seconds=86400):
        rows = (self._events()
                .where(HueyEvent.signal.is_null(False))
                .where(HueyEvent.ts > time.time() - seconds)
                .select(HueyEvent.signal, peewee.fn.COUNT(HueyEvent.id).alias('n'))
                .group_by(HueyEvent.signal))
        return dict(rows.tuples().iterator())

    def recent_events(self, limit=50):
        rows = (self._events().order_by(HueyEvent.id.desc()).limit(limit)
                .dicts())
        return [{'ts': r['ts'],
                 'time': time.strftime('%H:%M:%S', time.localtime(r['ts'])),
                 'task': r['task'].rsplit('.', 1)[-1], 'signal': r['signal'],
                 'duration': r['duration'], 'error': r['error']} for r in rows]

    def inflight(self):
        now = time.time()
        rows = (HueyInflight.select()
                .where(HueyInflight.queue == self.name)
                .order_by(HueyInflight.started).dicts())
        return [{'task': r['task'].rsplit('.', 1)[-1], 'id': r['task_id'],
                 'started': r['started'], 'elapsed': now - r['started']}
                for r in rows]

    def task_breakdown(self):
        agg = {}
        rows = (self._events()
                .select(HueyEvent.task, HueyEvent.signal,
                        peewee.fn.COUNT(HueyEvent.id).alias('n'),
                        peewee.fn.SUM(HueyEvent.duration).alias('dur'))
                .group_by(HueyEvent.task, HueyEvent.signal).tuples())
        for task, signal, n, dur in rows:
            agg.setdefault(task, {})[signal] = (n, dur or 0.0)
        out = []
        for task, signals in agg.items():
            completed, comp_dur = signals.get(S.SIGNAL_COMPLETE, (0, 0.0))
            out.append({
                'task': task.rsplit('.', 1)[-1], 'full': task,
                'executed': signals.get(S.SIGNAL_EXECUTING, (0, 0.0))[0],
                'completed': completed,
                'errors': signals.get(S.SIGNAL_ERROR, (0, 0.0))[0],
                'retries': signals.get(S.SIGNAL_RETRYING, (0, 0.0))[0],
                'avg': (comp_dur / completed) if completed else None})
        out.sort(key=lambda r: (r['executed'], r['completed']), reverse=True)
        return out

    def throughput(self, minutes=60):
        now = time.time()
        rows = (self._events()
                .where(HueyEvent.ts > now - minutes * 60,
                       HueyEvent.signal.in_([S.SIGNAL_COMPLETE, S.SIGNAL_ERROR]))
                .select(HueyEvent.ts, HueyEvent.signal).tuples())
        complete = [0] * minutes
        error = [0] * minutes
        for ts, signal in rows:
            idx = int((now - ts) // 60)
            if 0 <= idx < minutes:
                slot = minutes - 1 - idx
                if signal == S.SIGNAL_ERROR:
                    error[slot] += 1
                else:
                    complete[slot] += 1
        return {'complete': complete, 'error': error}

    def overview(self, seconds=86400):
        window = self.window_counts(seconds)
        completed = window.get(S.SIGNAL_COMPLETE, 0)
        errors = window.get(S.SIGNAL_ERROR, 0)
        total = completed + errors
        return {'completed': completed, 'errors': errors,
                'retries': window.get(S.SIGNAL_RETRYING, 0),
                'error_rate': (errors / total) if total else 0,
                'inflight': len(self.inflight())}


def live_counts(huey):
    data = {}
    for key, method in (('pending', huey.pending_count),
                        ('scheduled', huey.scheduled_count),
                        ('results', huey.result_count)):
        try:
            data[key] = method()
        except Exception:
            data[key] = None
    return data


def pending_tasks(huey, limit=50):
    try:
        return [{'task': type(t).__name__, 'id': t.id, 'priority': t.priority,
                 'eta': t.eta} for t in huey.pending(limit)]
    except Exception:
        return []


def scheduled_tasks(huey, limit=50):
    try:
        return [{'task': type(t).__name__, 'id': t.id, 'eta': t.eta}
                for t in huey.scheduled(limit)]
    except Exception:
        return []


def known_tasks(huey):
    out = []
    for full, task_class in sorted(huey._registry._registry.items()):
        try:
            revoked = huey.is_revoked(task_class)
        except Exception:
            revoked = False
        out.append({'full': full, 'task': task_class.__name__,
                    'revoked': revoked})
    return out


def dashboard_context(huey, stats, list_limit=50, event_limit=50,
                      throughput_minutes=60):
    stats_map = {row['full']: row for row in stats.task_breakdown()}
    known = known_tasks(huey)
    for row in known:
        row['stats'] = stats_map.get(row['full'])
    return {'live': live_counts(huey), 'overview': stats.overview(),
            'known': known, 'inflight': stats.inflight(),
            'events': stats.recent_events(event_limit),
            'pending': pending_tasks(huey, list_limit),
            'scheduled': scheduled_tasks(huey, list_limit),
            'throughput': stats.throughput(throughput_minutes)}


def enable_stats(huey, db, **kwargs):
    stats = getattr(huey, '_stats', None)
    if stats is None:
        stats = HueyStats(huey, db, **kwargs)
        huey._stats = stats
        stats.connect()
    return stats

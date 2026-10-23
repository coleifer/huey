import os
import threading
import time
import unittest
import warnings

try:
    import peewee
except ImportError:
    peewee = None

from huey import signals as S
from huey.tests.base import BaseTestCase

if peewee is not None:
    from huey.contrib import stats as stats_mod
    from huey.contrib.stats import HueyEvent
    from huey.contrib.stats import HueyInflight
    from huey.contrib.stats import HueyStats


@unittest.skipIf(peewee is None, 'requires peewee')
class StatsTestCase(BaseTestCase):
    db_file = '/tmp/huey-stats.db'

    def setUp(self):
        super(StatsTestCase, self).setUp()
        if os.path.exists(self.db_file):
            os.unlink(self.db_file)
        self.db = peewee.SqliteDatabase(self.db_file)
        stats_mod.database.initialize(self.db)
        self.stats = None

        @self.huey.task()
        def task_a():
            pass
        self.task_a = task_a

    def tearDown(self):
        if self.stats is not None:
            self.stats.close()
        if os.path.exists(self.db_file):
            os.unlink(self.db_file)
        super(StatsTestCase, self).tearDown()

    def get_stats(self, **kwargs):
        self.stats = HueyStats(self.huey, self.db, **kwargs)
        self.stats.connect()
        return self.stats


class TestStatsInit(StatsTestCase):
    def test_init_closes_own_connection(self):
        HueyStats(self.huey, self.db)
        self.assertTrue(self.db.is_closed())

    def test_init_preserves_open_connection(self):
        self.db.connect()
        HueyStats(self.huey, self.db)
        self.assertFalse(self.db.is_closed())
        self.db.close()


class TestResolveDb(StatsTestCase):
    def test_proxy_unwrap(self):
        proxy = peewee.DatabaseProxy()
        proxy.initialize(self.db)
        self.assertTrue(stats_mod._resolve_db(proxy) is self.db)

        class Wrapper(object):
            database = proxy
        self.assertTrue(stats_mod._resolve_db(Wrapper()) is self.db)

        self.assertRaises(TypeError, stats_mod._resolve_db, object())
        self.assertRaises(TypeError, stats_mod._resolve_db,
                          peewee.DatabaseProxy())


class TestStatsShutdown(StatsTestCase):
    def test_close_drains_what_the_writer_left_behind(self):
        # Real trigger: the writer takes a batch, more rows arrive while it is
        # writing, and the stop flag is set before it finishes. It re-checks
        # the flag before flushing again and exits, stranding the tail. That
        # state is reproduced here by stopping the writer with rows buffered.
        stats = self.get_stats(flush_interval=60)
        stats._stop.set()
        stats._wake.set()
        stats._writer.join(5)
        self.assertFalse(stats._writer.is_alive())

        for _ in range(3):
            self.huey._emit(S.SIGNAL_ENQUEUED, self.task_a.s())
        self.assertEqual(len(stats._buf), 3)
        self.assertEqual(HueyEvent.select().count(), 0)

        stats._stop.clear()          # close() is a no-op once stop is set
        stats.close()

        self.assertEqual(stats._buf, [])
        self.assertEqual(HueyEvent.select().count(), 3)

    def test_shutdown_hook_waits_for_writer(self):
        # A worker calls os._exit right after its shutdown hooks, so the hook
        # must not return while the writer is mid-flush.
        stats = self.get_stats(flush_interval=60)
        self.huey._emit(S.SIGNAL_ENQUEUED, self.task_a.s())
        hook = threading.Thread(target=self.huey._shutdown['huey_stats_flush'])
        with stats._flush_lock:  # Writer is mid-flush.
            hook.start()
            hook.join(0.1)
            self.assertTrue(hook.is_alive())
        hook.join()
        self.assertEqual(HueyEvent.select().count(), 1)


class TestStatsFlush(StatsTestCase):
    def test_inflight_collapse(self):
        stats = self.get_stats(flush_interval=60)
        t1, t2 = self.task_a.s(), self.task_a.s()
        self.huey._emit(S.SIGNAL_EXECUTING, t1)
        self.huey._emit(S.SIGNAL_EXECUTING, t2)
        self.huey._emit(S.SIGNAL_COMPLETE, t1)
        stats._flush()

        # All three events recorded, only the still-running task inflight.
        self.assertEqual(HueyEvent.select().count(), 3)
        self.assertEqual([r.task_id for r in HueyInflight.select()],
                         [str(t2.id)])

    def test_flush_large_batch(self):
        # flush_max above the batch size, so the writer thread never wakes
        # to race this thread's flush.
        stats = self.get_stats(flush_interval=60, flush_max=1000)
        for i in range(250):
            self.huey._emit(S.SIGNAL_ENQUEUED, self.task_a.s())
        stats._flush()
        self.assertEqual(HueyEvent.select().count(), 250)

    def test_attempt_enders_clear_inflight(self):
        stats = self.get_stats(flush_interval=60)
        signals = (S.SIGNAL_TIMEOUT, S.SIGNAL_LOCKED, S.SIGNAL_RATE_LIMITED,
                   S.SIGNAL_RETRYING)
        for signal in signals:
            t = self.task_a.s()
            self.huey._emit(S.SIGNAL_EXECUTING, t)
            self.huey._emit(signal, t)
        stats._flush()

        self.assertEqual(HueyInflight.select().count(), 0)
        rows = dict((e.signal, e.duration) for e in HueyEvent.select()
                    .where(HueyEvent.signal != S.SIGNAL_EXECUTING))
        self.assertEqual(sorted(rows), sorted(signals))
        self.assertTrue(all(d is not None for d in rows.values()))

    def test_recorder_failure_logged_not_raised(self):
        stats = self.get_stats(flush_interval=60)
        with self.assertLogs('huey.stats', 'ERROR'):
            stats._on_signal(S.SIGNAL_EXECUTING, None)
        self.assertEqual(stats._buf, [])

    def test_unrepresentable_args_still_record_the_event(self):
        stats = self.get_stats(flush_interval=60, capture_args=True)

        class Weird(object):
            def __repr__(self):
                raise RuntimeError('repr exploded')

        @self.huey.task()
        def takes_arg(x):
            pass

        self.huey._emit(S.SIGNAL_EXECUTING, takes_arg.s(Weird()))
        self.huey._emit(S.SIGNAL_COMPLETE, takes_arg.s(1))
        stats._flush()

        rows = {e.signal: e.args for e in HueyEvent.select()}
        self.assertEqual(sorted(rows), [S.SIGNAL_COMPLETE, S.SIGNAL_EXECUTING])
        self.assertEqual(rows[S.SIGNAL_EXECUTING], '<unrepresentable>')
        self.assertEqual(rows[S.SIGNAL_COMPLETE], '(1,) {}')

    def test_error_then_retry_duration_attributed_once(self):
        stats = self.get_stats(flush_interval=60)
        t = self.task_a.s()
        self.huey._emit(S.SIGNAL_EXECUTING, t)
        self.huey._emit(S.SIGNAL_ERROR, t)
        self.huey._emit(S.SIGNAL_RETRYING, t)
        stats._flush()

        self.assertEqual(HueyInflight.select().count(), 0)
        rows = dict((e.signal, e.duration) for e in HueyEvent.select())
        self.assertTrue(rows[S.SIGNAL_ERROR] is not None)
        self.assertTrue(rows[S.SIGNAL_RETRYING] is None)


class TestStatsPrune(StatsTestCase):
    def record(self, queue, prefix, n):
        now = time.time()
        HueyEvent.insert_many([
            {'ts': now, 'queue': queue, 'task_id': '%s%s' % (prefix, i),
             'task': 'tests.task_a', 'signal': S.SIGNAL_COMPLETE}
            for i in range(n)]).execute()

    def prune(self, stats):
        stats._prune_at = 0
        stats._maybe_prune()

    def test_max_events_scoped_per_queue(self):
        # Event ids autoincrement across queues, so a prune based on an id
        # window would retain far fewer than max_events per queue.
        stats = self.get_stats(flush_interval=60, max_events=5)
        self.record(self.huey.name, 'a', 3)
        self.record('other', 'x', 10)
        self.record(self.huey.name, 'b', 4)
        self.prune(stats)

        query = (HueyEvent.select()
                 .where(HueyEvent.queue == self.huey.name)
                 .order_by(HueyEvent.id))
        self.assertEqual([e.task_id for e in query],
                         ['a2', 'b0', 'b1', 'b2', 'b3'])
        self.assertEqual(HueyEvent.select()
                         .where(HueyEvent.queue == 'other').count(), 10)

    def test_inflight_hours(self):
        stats = self.get_stats(flush_interval=60, inflight_hours=1)
        now = time.time()
        HueyInflight.insert_many([
            {'task_id': 'told', 'queue': self.huey.name, 'task': 't',
             'started': now - 3700},
            {'task_id': 'tnew', 'queue': self.huey.name, 'task': 't',
             'started': now - 60}]).execute()
        self.prune(stats)
        self.assertEqual([r.task_id for r in HueyInflight.select()], ['tnew'])


class TestDashboardContext(StatsTestCase):
    def test_unregistered_tasks_still_listed(self):
        # A web process does not import the consumer's tasks module, so the
        # table must fall back to whatever the recorder has actually seen.
        stats = self.get_stats(flush_interval=60)
        t = self.task_a.s()
        self.huey._emit(S.SIGNAL_EXECUTING, t)
        self.huey._emit(S.SIGNAL_COMPLETE, t)
        stats._flush()

        full = stats_mod.known_tasks(self.huey)[0]['full']
        self.task_a.unregister()
        self.assertEqual(stats_mod.known_tasks(self.huey), [])

        rows = stats_mod.dashboard_context(self.huey, stats)['known']
        self.assertEqual([r['full'] for r in rows], [full])
        self.assertFalse(rows[0]['registered'])
        self.assertEqual(rows[0]['stats']['completed'], 1)

    def test_registered_tasks_are_marked(self):
        stats = self.get_stats(flush_interval=60)
        rows = stats_mod.dashboard_context(self.huey, stats)['known']
        self.assertTrue(rows[0]['registered'])
        self.assertTrue(rows[0]['stats'] is None)


class TestSearchEvents(StatsTestCase):
    def emit(self, task, signal, error=None):
        self.huey._emit(signal, task, error)

    def setup_events(self):
        stats = self.get_stats(flush_interval=60)

        @self.huey.task()
        def task_b():
            pass

        a, b = self.task_a.s(), task_b.s()
        self.emit(a, S.SIGNAL_EXECUTING)
        self.emit(a, S.SIGNAL_COMPLETE)
        self.emit(b, S.SIGNAL_EXECUTING)
        self.emit(b, S.SIGNAL_ERROR, ValueError('kapow'))
        stats._flush()
        return stats

    def test_no_filters_returns_everything_newest_first(self):
        stats = self.setup_events()
        total, rows = stats.search_events()
        self.assertEqual(total, 4)
        self.assertEqual([r['signal'] for r in rows],
                         [S.SIGNAL_ERROR, S.SIGNAL_EXECUTING,
                          S.SIGNAL_COMPLETE, S.SIGNAL_EXECUTING])

    def test_filter_by_signal(self):
        stats = self.setup_events()
        total, rows = stats.search_events(signal=S.SIGNAL_EXECUTING)
        self.assertEqual(total, 2)
        self.assertTrue(all(r['signal'] == S.SIGNAL_EXECUTING for r in rows))

    def test_filter_by_task(self):
        stats = self.setup_events()
        name = stats.event_tasks()[0]
        total, rows = stats.search_events(task=name)
        self.assertEqual(total, 2)
        self.assertTrue(all(r['task_full'] == name for r in rows))

    def test_search_matches_error_task_and_id(self):
        stats = self.setup_events()
        total, rows = stats.search_events(q='kapow')
        self.assertEqual(total, 1)
        self.assertTrue('kapow' in rows[0]['error'])

        total, _ = stats.search_events(q='task_b')
        self.assertEqual(total, 2)

        task_id = stats.search_events()[1][0]['task_id']
        total, rows = stats.search_events(q=task_id)
        self.assertEqual(total, 2)  # executing + error for that task

        self.assertEqual(stats.search_events(q='nope')[0], 0)

    def test_filters_combine(self):
        stats = self.setup_events()
        total, _ = stats.search_events(signal=S.SIGNAL_EXECUTING, q='kapow')
        self.assertEqual(total, 0)

    def test_pagination(self):
        stats = self.setup_events()
        total, page1 = stats.search_events(limit=3, offset=0)
        self.assertEqual((total, len(page1)), (4, 3))

        total, page2 = stats.search_events(limit=3, offset=3)
        self.assertEqual((total, len(page2)), (4, 1))

        ids = [r['ts'] for r in page1] + [r['ts'] for r in page2]
        self.assertEqual(len(set(ids)), len(ids))  # no overlap

    def test_ordered_by_event_time_not_insert_order(self):
        # The producer records "enqueued" and the consumer records the rest,
        # each with its own flush buffer, so insert order is a race. Ordering
        # by row id put "enqueued" above the "complete" that followed it.
        stats = self.get_stats(flush_interval=60)
        now = time.time()
        rows = [{'ts': now + offset, 'queue': self.huey.name, 'task_id': 'abc',
                 'task': 'x.y', 'signal': signal, 'duration': None,
                 'error': None, 'args': None}
                for offset, signal in ((0.2, S.SIGNAL_EXECUTING),
                                       (0.4, S.SIGNAL_COMPLETE),
                                       (0.0, S.SIGNAL_ENQUEUED))]
        HueyEvent.insert_many(rows).execute()

        expected = [S.SIGNAL_COMPLETE, S.SIGNAL_EXECUTING, S.SIGNAL_ENQUEUED]
        self.assertEqual([r['signal'] for r in stats.search_events()[1]],
                         expected)
        self.assertEqual([r['signal'] for r in stats.recent_events()],
                         expected)

    def test_search_treats_wildcards_literally(self):
        # A user typing "%" or "a_b" into the search box means those
        # characters, not LIKE wildcards.
        stats = self.get_stats(flush_interval=60)
        rows = [{'ts': 100.0 + i, 'queue': self.huey.name, 'task_id': 'id%s' % i,
                 'task': task, 'signal': S.SIGNAL_ERROR, 'duration': None,
                 'error': error, 'args': None}
                for i, (task, error) in enumerate((
                    ('app.alpha', None),
                    ('app.pct', 'failed at 100% cpu'),
                    ('app.under', 'a_b mismatch')))]
        HueyEvent.insert_many(rows).execute()

        self.assertEqual(stats.search_events(q='%')[0], 1)
        self.assertEqual(stats.search_events(q='_')[0], 1)
        self.assertEqual(stats.search_events(q='100%')[0], 1)
        self.assertEqual(stats.search_events(q='a_b')[0], 1)
        self.assertEqual(stats.search_events(q='a_pha')[0], 0)
        self.assertEqual(stats.search_events(q='alpha')[0], 1)
        self.assertEqual(stats.search_events(q='ALPHA')[0], 1)
        self.assertEqual(stats.search_events(q='\\')[0], 0)
        self.assertEqual(stats.search_events(q="';drop table huey_event;--")[0], 0)
        self.assertEqual(stats.search_events()[0], 3)   # table intact

    def test_filter_options(self):
        stats = self.setup_events()
        self.assertEqual(stats.event_signals(),
                         sorted([S.SIGNAL_COMPLETE, S.SIGNAL_ERROR,
                                 S.SIGNAL_EXECUTING]))
        self.assertEqual(len(stats.event_tasks()), 2)

    def test_scoped_to_this_queue(self):
        stats = self.setup_events()
        stats.name = 'other-queue'
        self.assertEqual(stats.search_events()[0], 0)
        self.assertEqual(stats.event_signals(), [])


@unittest.skipIf(not hasattr(os, 'register_at_fork'), 'requires fork()')
class TestStatsFork(StatsTestCase):
    def fork_child(self, child_fn):
        with warnings.catch_warnings():
            # Forking with the writer thread running is the scenario under
            # test. Silence the 3.12+ fork-in-threaded-process warning.
            warnings.simplefilter('ignore', DeprecationWarning)
            pid = os.fork()
        if pid == 0:
            # The child must exit here. Returning would resume the test
            # runner inside the fork. Exit code 3 means child_fn raised.
            try:
                code = child_fn()
            except BaseException:
                code = 3
            os._exit(code)
        _, status = os.waitpid(pid, 0)
        self.assertTrue(os.WIFEXITED(status))
        return os.WEXITSTATUS(status)

    def test_writer_restarted_in_child(self):
        stats = self.get_stats(flush_interval=0.05)
        parent_writer = stats._writer
        task = self.task_a.s()

        def child():
            if stats._writer is parent_writer or not stats._writer.is_alive():
                return 1
            self.huey._emit(S.SIGNAL_EXECUTING, task)
            self.huey._emit(S.SIGNAL_COMPLETE, task)
            deadline = time.time() + 5
            while time.time() < deadline:
                query = HueyEvent.select().where(
                    HueyEvent.signal == S.SIGNAL_COMPLETE)
                if query.count() == 1:
                    return 0
                time.sleep(0.02)
            return 2

        self.assertEqual(self.fork_child(child), 0)
        self.assertTrue(parent_writer.is_alive())
        self.assertEqual(
            sorted(e.signal for e in HueyEvent.select()),
            [S.SIGNAL_COMPLETE, S.SIGNAL_EXECUTING])

    def test_buffered_rows_written_by_parent_alone(self):
        stats = self.get_stats(flush_interval=60)
        self.huey._emit(S.SIGNAL_ENQUEUED, self.task_a.s())
        self.assertEqual(len(stats._buf), 1)

        def child():
            if stats._buf:
                return 1
            return 0

        self.assertEqual(self.fork_child(child), 0)

        stats._flush()
        query = HueyEvent.select().where(HueyEvent.signal == S.SIGNAL_ENQUEUED)
        self.assertEqual(query.count(), 1)

    def test_shutdown_hook_flushes_in_child(self):
        # flush_interval=60 so only the shutdown hook can have written it.
        self.get_stats(flush_interval=60)

        def child():
            self.huey._emit(S.SIGNAL_EXECUTING, self.task_a.s())
            for hook in self.huey._shutdown.values():
                hook()
            return 0 if HueyEvent.select().count() == 1 else 1

        self.assertEqual(self.fork_child(child), 0)

    def test_closed_recorder_not_revived(self):
        stats = self.get_stats()
        stats.close()
        parent_writer = stats._writer
        def child():
            if stats._writer is parent_writer:
                return 0
            return 1

        self.assertEqual(self.fork_child(child), 0)

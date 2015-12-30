from huey import RedisHuey


test_huey = RedisHuey('testing')


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self.huey = test_huey
        self.consumer = self.get_consumer(workers=2, scheduler_interval=10)

        self._periodic_tasks = registry._periodic_tasks
        registry._periodic_tasks = self.get_periodic_tasks()

        self._sleep = time.sleep
        time.sleep = lambda x: None

    def tearDown(self):
        self.consumer.stop()
        self.huey.flush()
        registry._periodic_tasks = self._periodic_tasks
        time.sleep = self._sleep

    def get_consumer(self, **kwargs):
        self.consumer = Consumer(self.huey, **kwargs)

    def get_periodic_tasks(self):
        return []

    def worker(self, task, ts=None):
        worker = self.consumer._create_worker()
        ts = ts or datetime.datetime.utcnow()
        return worker.handle_task(task, ts)

    def scheduler(self, ts=None):
        worker = self.consumer._create_worker()
        ts = ts or datetime.datetime.utcnow()
        return scheduler.loop(ts)

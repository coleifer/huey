from huey.tests.consumer import *
import datetime

# create a dummy config for passing to the consumer
class CPUDummyConfiguration(DummyConfiguration):
    QUEUE = mp_test_queue
    RESULT_STORE = mp_test_result_store
    TASK_STORE = mp_test_task_store
    THREADS = multiprocessing.cpu_count()

cpu_invoker = Invoker(mp_test_queue, mp_test_result_store, mp_test_task_store)

def fib(n):
    if n == 0:
        return 0
    elif n == 1:
        return 1
    else:
        return fib(n-1) + fib(n-2)

@queue_command(cpu_invoker)
def stress_cpu(n):
    return fib(n)


class SkewCPUTestCase(unittest.TestCase):
    ConsumerCls = Consumer
    IQCls = IterableQueue
    
    def setUp(self):
        ConsumerCls = self.ConsumerCls
        self.consumer = ConsumerCls(cpu_invoker, CPUDummyConfiguration)
        self.consumer.invoker.queue.flush()
        self.consumer.invoker.result_store.flush()
        self.consumer.schedule.schedule_dict().clear()

        self.handler = TestLogHandler()
        self.consumer.logger.addHandler(self.handler)

    def tearDown(self):
        self.consumer.shutdown()
        self.consumer.logger.removeHandler(self.handler)

    def test_stress_cpu(self):
        self.consumer.start_message_receiver()
        self.consumer.start_worker_pool()

        start = datetime.datetime.now()

        results = []
        for i in xrange(CPUDummyConfiguration.THREADS):
            results.append(stress_cpu(35))

        for res in results:
            value = res.get(blocking=True)
            self.assertEqual(value, 9227465)

        end = datetime.datetime.now()

        print "\nComputation took %s seconds" % (end - start).seconds

class SkewMPCPUTestCase(SkewCPUTestCase):
    ConsumerCls = MPConsumer
    IQCls = MPIterableQueue

__all__ = ["SkewCPUTestCase", "SkewMPCPUTestCase"]

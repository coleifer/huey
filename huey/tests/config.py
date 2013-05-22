from huey import Huey
from huey.backends.dummy import DummyDataStore
from huey.backends.dummy import DummyQueue
from huey.backends.dummy import DummySchedule


test_queue = DummyQueue('test-queue')
test_result_store = DummyDataStore('test-results')
test_schedule = DummySchedule('test-schedule')

test_huey = Huey(test_queue, test_result_store, test_schedule)

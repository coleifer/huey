from huey import Huey
from huey.backends.dummy import DummyDataStore
from huey.backends.dummy import DummyQueue


test_queue = DummyQueue('test-queue')
test_result_store = DummyDataStore('test-results')

test_huey = Huey(test_queue, test_result_store)

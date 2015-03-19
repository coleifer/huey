# -*- coding:utf-8 -*-
import pickle
import time
import json
import threading

from huey.backends.base import BaseQueue, BaseSchedule, BaseDataStore, BaseEventEmitter
from huey.djhuey.models import HueyQueue, HueySchedule, HueyResult, HueyEvent
from huey.utils import EmptyData


def synchronized_method(method):
    outer_lock = threading.Lock()
    lock_name = "__" + method.__name__ + "_lock" + "__"

    def sync_method(self, *args, **kws):
        with outer_lock:
            if not hasattr(self, lock_name):
                setattr(self, lock_name, threading.Lock())
            lock = getattr(self, lock_name)
            with lock:
                return method(self, *args, **kws)

    return sync_method


class DjangoQueue(BaseQueue):
    def __init__(self, name, alias):
        super(DjangoQueue, self).__init__(name, alias=alias)
        self._alias = alias

    def write(self, data):
        HueyQueue.objects.using(self._alias).create(item=data)

    @synchronized_method
    def read(self):
        try:
            obj = HueyQueue.objects.using(self._alias).all().order_by('id')[0]
            obj.delete(self._alias)
            return str(obj.item)
        except IndexError:
            return None

    def remove(self, data):
        HueyQueue.objects.using(self._alias).filter(item=data).delete()

    def flush(self):
        HueyQueue.objects.using(self._alias).all().delete()

    def __len__(self):
        return HueyQueue.objects.using(self._alias).all().count()


def convert_ts(ts):
    return time.mktime(ts.timetuple())


class DjangoSchedule(BaseSchedule):
    def __init__(self, name, alias):
        super(DjangoSchedule, self).__init__(name, alias=alias)
        self._alias = alias

    def add(self, data, ts):
        HueySchedule.objects.using(self._alias).create(item=pickle.dumps(data), ts=convert_ts(ts))

    def read(self, ts):
        qs = HueySchedule.objects.using(self._alias).filter(ts__lte=convert_ts(ts))
        items = [pickle.loads(s.item) for s in qs.order_by('ts')]
        qs.delete()
        return items

    def flush(self):
        HueySchedule.objects.using(self._alias).all().delete()


class DjangoDataStore(BaseDataStore):
    def __init__(self, name, alias):
        super(DjangoDataStore, self).__init__(name, alias=alias)
        self._alias = alias

    def put(self, key, value):
        HueyResult.objects.using(self._alias).filter(key=key).delete()
        HueyResult.objects.using(self._alias).create(key=key, result=pickle.dumps(value))

    def peek(self, key):
        try:
            return pickle.loads(HueyResult.objects.using(self._alias).get(key=key).result)
        except HueyResult.DoesNotExist:
            return EmptyData

    def get(self, key):
        try:
            result = pickle.loads(HueyResult.objects.using(self._alias).get(key=key).result)
            HueyResult.objects.using(self._alias).filter(key=key).delete()
            return result
        except HueyResult.DoesNotExist:
            return EmptyData

    def flush(self):
        HueyResult.objects.using(self._alias).all().delete()


class DjangoEventEmitter(BaseEventEmitter):
    def __init__(self, channel, alias, size=500):
        super(DjangoEventEmitter, self).__init__(channel, alias=alias)
        self._alias = alias
        self._size = size

    def emit(self, message):
        HueyEvent.objects.using(self._alias).create(channel=self.channel, message=message)
        if HueyEvent.objects.using(self._alias).filter(channel=self.channel).count() > self._size:
            old_qs = HueyEvent.objects.using(self._alias).filter(channel=self.channel).order_by('pk')
            HueyEvent.objects.using(self._alias).filter(pk_in=old_qs.values_list('pk')[:self._size - 200]).delete()

    def read(self):
        wait = 0.1  # Initial wait period
        max_wait = 2  # Maximum wait duration
        tries = 0

        try:
            last_id = HueyEvent.objects.using(self._alias).filter(channel=self.channel).order_by('-pk')[0].pk
        except IndexError:
            last_id = 0

        while True:
            try:
                recent_id = HueyEvent.objects.using(self._alias).filter(channel=self.channel).order_by('-pk')[0].pk
            except IndexError:
                recent_id = 0

            if recent_id != last_id:
                qs = HueyEvent.objects.using(self._alias).filter(channel=self.channel).order_by('-pk')
                return [json.loads(obj.message) for obj in qs[:recent_id - last_id]]
            else:
                tries += 1
                time.sleep(wait)
                # Increase the wait period
                wait = min(max_wait, tries / 10 + wait)


Components = (DjangoQueue, DjangoDataStore, DjangoSchedule, DjangoEventEmitter)

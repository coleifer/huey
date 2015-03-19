# -*- coding:utf-8 -*-
from django.db import models
from django.utils.translation import ugettext_lazy as _


class HueyQueue(models.Model):
    class Meta:
        db_table = 'huey_queue'

    item = models.TextField()
    created = models.DateTimeField(auto_now=True, editable=False)


class HueySchedule(models.Model):
    class Meta:
        db_table = 'huey_schedule'

    item = models.TextField()
    ts = models.PositiveIntegerField(db_index=True)
    created = models.DateTimeField(auto_now=True, editable=False)


class HueyResult(models.Model):
    class Meta:
        db_table = 'huey_result'

    key = models.CharField(max_length=255, db_index=True)
    result = models.TextField()
    created = models.DateTimeField(auto_now=True, editable=False)


class HueyEvent(models.Model):
    class Meta:
        db_table = 'huey_event'

    channel = models.CharField(max_length=255, db_index=True)
    message = models.TextField()
    created = models.DateTimeField(auto_now=True, editable=False)

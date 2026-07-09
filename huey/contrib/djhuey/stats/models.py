from django.db import models


class HueyEvent(models.Model):
    ts = models.FloatField(db_index=True)
    queue = models.CharField(max_length=255, db_index=True)
    task_id = models.CharField(max_length=255)
    task = models.CharField(max_length=255, db_index=True)
    signal = models.CharField(max_length=64)
    duration = models.FloatField(null=True)
    error = models.TextField(null=True)
    args = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = 'huey_event'
        verbose_name = 'event'

    def __str__(self):
        return '%s %s' % (self.task, self.signal)


class HueyDashboard(HueyEvent):
    class Meta:
        proxy = True
        verbose_name = 'dashboard'
        verbose_name_plural = 'dashboard'

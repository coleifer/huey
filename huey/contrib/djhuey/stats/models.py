from django.db import models


# Never queried, gives the admin an entry and URLs to hang the dashboard on.
class HueyDashboard(models.Model):
    class Meta:
        managed = False
        verbose_name = 'dashboard'
        verbose_name_plural = 'dashboard'

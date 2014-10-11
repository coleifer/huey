# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='HueyEvent',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now=True, editable=False)),
                ('channel', models.CharField(max_length=255, db_index=True)),
                ('message', models.TextField()),
            ],
            options={
                'db_table': 'huey_event',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='HueyQueue',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now=True, editable=False)),
                ('item', models.TextField()),
            ],
            options={
                'db_table': 'huey_queue',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='HueyResult',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now=True, editable=False)),
                ('key', models.CharField(max_length=255, db_index=True)),
                ('result', models.TextField()),
            ],
            options={
                'db_table': 'huey_result',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='HueySchedule',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now=True, editable=False)),
                ('item', models.TextField()),
                ('ts', models.PositiveIntegerField(db_index=True)),
            ],
            options={
                'db_table': 'huey_schedule',
            },
            bases=(models.Model,),
        ),
    ]

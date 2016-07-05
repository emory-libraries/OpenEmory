# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='HarvestRecord',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('pmcid', models.IntegerField(verbose_name=b'PubMed Central ID', unique=True, editable=False)),
                ('title', models.TextField(verbose_name=b'Article Title')),
                ('harvested', models.DateTimeField(auto_now_add=True, verbose_name=b'Date Harvested')),
                ('status', models.CharField(default=b'harvested', max_length=25, choices=[(b'harvested', b'harvested'), (b'inprocess', b'inprocess'), (b'ingested', b'ingested'), (b'ignored', b'ignored')])),
                ('fulltext', models.BooleanField(editable=False)),
                ('content', models.FileField(upload_to=b'harvest/%Y/%m/%d', blank=True)),
                ('authors', models.ManyToManyField(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'permissions': (('view_harvestrecord', 'Can see available harvested records'), ('ingest_harvestrecord', 'Can ingest harvested record to Fedora'), ('ignore_harvestrecord', 'Can mark a harvested record as ignored')),
            },
        ),
    ]

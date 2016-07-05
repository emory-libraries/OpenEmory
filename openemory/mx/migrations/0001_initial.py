# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('downtime', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Banner',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_modified', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(help_text='The title that will display on the banner. \nMax length of 25 characters.', max_length=25)),
                ('message', models.CharField(help_text='The message to be shown in the banner. \nMax length of 140 characters.', max_length=140)),
                ('days', models.PositiveIntegerField(help_text='Number of days previous to the downtime period to show the banner.')),
                ('disabled', models.BooleanField(default=False)),
                ('show_on_date', models.DateTimeField(help_text='The date which the banner will be eligable to be shown.', null=True, editable=False, blank=True)),
                ('period', models.ForeignKey(help_text='The downtime associated with this banner. \nUsed to define when to show banner.', to='downtime.Period')),
            ],
            options={
                'verbose_name': 'Downtime Banner',
                'verbose_name_plural': 'Downtime Banners',
            },
        ),
    ]

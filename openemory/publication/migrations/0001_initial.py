# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ArticleRecord',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
            ],
            options={
                'permissions': (('review_article', 'Can review articles'), ('view_embargoed', 'Can view embargoed content'), ('view_admin_metadata', 'Can view admin metadata content')),
            },
        ),
        migrations.CreateModel(
            name='ArticleStatistics',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('pid', models.CharField(max_length=50)),
                ('year', models.IntegerField()),
                ('quarter', models.IntegerField()),
                ('num_views', models.IntegerField(default=0, help_text=b'metadata view page loads')),
                ('num_downloads', models.IntegerField(default=0, help_text=b'article PDF downloads')),
            ],
            options={
                'verbose_name_plural': 'Article Statistics',
            },
        ),
        migrations.CreateModel(
            name='FeaturedArticle',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('pid', models.CharField(unique=True, max_length=60)),
            ],
        ),
        migrations.CreateModel(
            name='LastRun',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('start_time', models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name='License',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('short_name', models.CharField(unique=True, max_length=30)),
                ('title', models.CharField(unique=True, max_length=100)),
                ('version', models.CharField(max_length=5)),
                ('url', models.URLField(unique=True)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='articlestatistics',
            unique_together=set([('pid', 'year', 'quarter')]),
        ),
    ]

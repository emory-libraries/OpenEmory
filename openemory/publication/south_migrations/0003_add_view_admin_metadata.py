# file openemory/publication/migrations/0003_add_view_admin_metadata.py
# 
#   Copyright 2010 Emory University General Library
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

# encoding: utf-8
import datetime
from south.db import db
from south.v2 import DataMigration
from django.contrib.auth.models import Permission, Group
from django.db import models


class Migration(DataMigration):

    depends_on = (
        ("accounts", "0009_load_site_admin_group"),
    )

    def forwards(self, orm):
        p = Permission.objects.get(codename='view_admin_metadata')
        g = Group.objects.get(name='Site Admin')
        g.permissions.add(p)
        g.save()


    def backwards(self, orm):
        p = Permission.objects.get(codename='view_admin_metadata')
        g = Group.objects.get(name='Site Admin')
        g.permissions.remove(p)


    models = {
        'publication.articlerecord': {
            'Meta': {'object_name': 'ArticleRecord'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'})
        },
        'publication.articlestatistics': {
            'Meta': {'unique_together': "(('pid', 'year'),)", 'object_name': 'ArticleStatistics'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'num_downloads': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'num_views': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'pid': ('django.db.models.fields.CharField', [], {'max_length': '50'}),
            'year': ('django.db.models.fields.IntegerField', [], {})
        }
    }

    complete_apps = ['publication']

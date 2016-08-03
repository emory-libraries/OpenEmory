# file openemory/publication/migrations/0002_auto__add_articlestatistics__add_unique_articlestatistics_pid_year.py
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
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Adding model 'ArticleStatistics'
        db.create_table('publication_articlestatistics', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('pid', self.gf('django.db.models.fields.CharField')(max_length=50)),
            ('year', self.gf('django.db.models.fields.IntegerField')()),
            ('num_views', self.gf('django.db.models.fields.IntegerField')(default=0)),
            ('num_downloads', self.gf('django.db.models.fields.IntegerField')(default=0)),
        ))
        db.send_create_signal('publication', ['ArticleStatistics'])

        # Adding unique constraint on 'ArticleStatistics', fields ['pid', 'year']
        db.create_unique('publication_articlestatistics', ['pid', 'year'])


    def backwards(self, orm):
        
        # Removing unique constraint on 'ArticleStatistics', fields ['pid', 'year']
        db.delete_unique('publication_articlestatistics', ['pid', 'year'])

        # Deleting model 'ArticleStatistics'
        db.delete_table('publication_articlestatistics')


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

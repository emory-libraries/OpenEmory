# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Removing unique constraint on 'ArticleStatistics', fields ['pid', 'year']
        db.delete_unique('publication_articlestatistics', ['pid', 'year'])

        # Adding field 'ArticleStatistics.quarter'
        db.add_column('publication_articlestatistics', 'quarter',
                      self.gf('django.db.models.fields.IntegerField')(default=-1),
                      keep_default=False)

        # Adding unique constraint on 'ArticleStatistics', fields ['quarter', 'pid', 'year']
        db.create_unique('publication_articlestatistics', ['quarter', 'pid', 'year'])

    def backwards(self, orm):
        # Removing unique constraint on 'ArticleStatistics', fields ['quarter', 'pid', 'year']
        db.delete_unique('publication_articlestatistics', ['quarter', 'pid', 'year'])

        # Deleting field 'ArticleStatistics.quarter'
        db.delete_column('publication_articlestatistics', 'quarter')

        # Adding unique constraint on 'ArticleStatistics', fields ['pid', 'year']
        db.create_unique('publication_articlestatistics', ['pid', 'year'])

    models = {
        'publication.articlerecord': {
            'Meta': {'object_name': 'ArticleRecord'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'})
        },
        'publication.articlestatistics': {
            'Meta': {'unique_together': "(('pid', 'year', 'quarter'),)", 'object_name': 'ArticleStatistics'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'num_downloads': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'num_views': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'pid': ('django.db.models.fields.CharField', [], {'max_length': '50'}),
            'quarter': ('django.db.models.fields.IntegerField', [], {}),
            'year': ('django.db.models.fields.IntegerField', [], {})
        }
    }

    complete_apps = ['publication']
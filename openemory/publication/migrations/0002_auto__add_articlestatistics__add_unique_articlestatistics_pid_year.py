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

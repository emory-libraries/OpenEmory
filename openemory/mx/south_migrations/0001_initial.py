# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Banner'
        db.create_table(u'mx_banner', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('created_at', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, blank=True)),
            ('last_modified', self.gf('django.db.models.fields.DateTimeField')(auto_now=True, blank=True)),
            ('title', self.gf('django.db.models.fields.CharField')(max_length=25)),
            ('message', self.gf('django.db.models.fields.CharField')(max_length=140)),
            ('period', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['downtime.Period'])),
            ('days', self.gf('django.db.models.fields.PositiveIntegerField')()),
        ))
        db.send_create_signal(u'mx', ['Banner'])


    def backwards(self, orm):
        # Deleting model 'Banner'
        db.delete_table(u'mx_banner')


    models = {
        u'downtime.period': {
            'Meta': {'object_name': 'Period'},
            'enabled': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'end_time': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'start_time': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'})
        },
        u'mx.banner': {
            'Meta': {'object_name': 'Banner'},
            'created_at': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'days': ('django.db.models.fields.PositiveIntegerField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'last_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'message': ('django.db.models.fields.CharField', [], {'max_length': '140'}),
            'period': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['downtime.Period']"}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '25'})
        }
    }

    complete_apps = ['mx']
# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'DowntimePeriod'
        db.create_table(u'mx_downtimeperiod', (
            (u'period_ptr', self.gf('django.db.models.fields.related.OneToOneField')(to=orm['downtime.Period'], unique=True, primary_key=True)),
        ))
        db.send_create_signal(u'mx', ['DowntimePeriod'])


        # Changing field 'Banner.period'
        db.alter_column(u'mx_banner', 'period_id', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['mx.DowntimePeriod']))

    def backwards(self, orm):
        # Deleting model 'DowntimePeriod'
        db.delete_table(u'mx_downtimeperiod')


        # Changing field 'Banner.period'
        db.alter_column(u'mx_banner', 'period_id', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['downtime.Period']))

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
            'disabled': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'last_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'message': ('django.db.models.fields.CharField', [], {'max_length': '140'}),
            'period': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['mx.DowntimePeriod']"}),
            'show_on_date': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '25'})
        },
        u'mx.downtimeperiod': {
            'Meta': {'object_name': 'DowntimePeriod', '_ormbases': [u'downtime.Period']},
            u'period_ptr': ('django.db.models.fields.related.OneToOneField', [], {'to': u"orm['downtime.Period']", 'unique': 'True', 'primary_key': 'True'})
        }
    }

    complete_apps = ['mx']
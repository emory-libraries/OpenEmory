# file openemory/accounts/migrations/0005_auto__add_field_userprofile_biography.py
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
        
        # Adding field 'UserProfile.biography'
        db.add_column('accounts_userprofile', 'biography', self.gf('django.db.models.fields.TextField')(default='', blank=True), keep_default=False)


    def backwards(self, orm):
        
        # Deleting field 'UserProfile.biography'
        db.delete_column('accounts_userprofile', 'biography')


    models = {
        'accounts.bookmark': {
            'Meta': {'object_name': 'Bookmark'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'pid': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['auth.User']"})
        },
        'accounts.degree': {
            'Meta': {'object_name': 'Degree'},
            'holder': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['accounts.UserProfile']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'institution': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '30'}),
            'year': ('django.db.models.fields.IntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'})
        },
        'accounts.esdperson': {
            'Meta': {'object_name': 'EsdPerson', 'db_table': '\'"esdv"."v_oem_fclt"\'', 'managed': 'False', 'db_tablespace': "'esdv'"},
            'ad_name': ('django.db.models.fields.CharField', [], {'max_length': '75', 'db_column': "'prsn_n_dspl_acdr'"}),
            'department_id': ('django.db.models.fields.CharField', [], {'max_length': '10', 'db_column': "'dprt_c'"}),
            'department_name': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_column': "'dprt8dtry_n'"}),
            'directory_name': ('django.db.models.fields.CharField', [], {'max_length': '75', 'db_column': "'prsn_n_full_dtry'"}),
            'directory_suppressed': ('openemory.accounts.fields.YesNoBooleanField', [], {'default': 'False', 'db_column': "'prsn_f_sprs_dtry'"}),
            'division_code': ('django.db.models.fields.CharField', [], {'max_length': '10', 'db_column': "'dvsn_i'"}),
            'division_name': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_column': "'dvsn8dtry_n'"}),
            'email': ('django.db.models.fields.CharField', [], {'max_length': '100', 'db_column': "'emad_n'"}),
            'email_forward': ('django.db.models.fields.CharField', [], {'max_length': '100', 'db_column': "'emad8frwd_n'"}),
            'employee_status': ('django.db.models.fields.CharField', [], {'max_length': '1', 'db_column': "'emjo_c_stts_empe'"}),
            'faculty_flag': ('openemory.accounts.fields.YesNoBooleanField', [], {'default': 'False', 'max_length': '1', 'db_column': "'empe_f_fclt'"}),
            'fax': ('django.db.models.fields.CharField', [], {'max_length': '12', 'db_column': "'prad_a_fax_empe_fmtt'"}),
            'firstmid_name': ('django.db.models.fields.CharField', [], {'max_length': '20', 'db_column': "'prsn_n_fm_dtry'"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True', 'db_column': "'prsn_i'"}),
            'information_suppressed': ('openemory.accounts.fields.YesNoBooleanField', [], {'default': 'False', 'db_column': "'prsn_f_sprs_infr'"}),
            'internet_suppressed': ('openemory.accounts.fields.YesNoBooleanField', [], {'default': 'False', 'db_column': "'prsn_f_sprs_intt'"}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '25', 'db_column': "'prsn_n_last_dtry'"}),
            'mailstop_code': ('django.db.models.fields.CharField', [], {'max_length': '12', 'db_column': "'mlst_i'"}),
            'mailstop_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'db_column': "'mlst_n'"}),
            'name_suffix': ('django.db.models.fields.CharField', [], {'max_length': '15', 'db_column': "'prsn_n_sufx_dtry'"}),
            'netid': ('django.db.models.fields.CharField', [], {'max_length': '8', 'db_column': "'logn8ntwr_i'"}),
            'person_type': ('django.db.models.fields.CharField', [], {'max_length': '1', 'db_column': "'prsn_c_type'"}),
            'phone': ('django.db.models.fields.CharField', [], {'max_length': '12', 'db_column': "'prad_a_tlph_empe_fmtt'"}),
            'ppid': ('django.db.models.fields.CharField', [], {'max_length': '8', 'db_column': "'prsn_i_pblc'"}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '70', 'db_column': "'prsn_e_titl_dtry'"})
        },
        'accounts.userprofile': {
            'Meta': {'object_name': 'UserProfile'},
            'biography': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'dept_num': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'employee_num': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'full_name': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'hr_id': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'phone': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'photo': ('django.db.models.fields.files.ImageField', [], {'default': "''", 'max_length': '100', 'blank': 'True'}),
            'show_suppressed': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'subdept_code': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.OneToOneField', [], {'to': "orm['auth.User']", 'unique': 'True'})
        },
        'auth.group': {
            'Meta': {'object_name': 'Group'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        'auth.permission': {
            'Meta': {'ordering': "('content_type__app_label', 'content_type__model', 'codename')", 'unique_together': "(('content_type', 'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'taggit.tag': {
            'Meta': {'object_name': 'Tag'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'slug': ('django.db.models.fields.SlugField', [], {'unique': 'True', 'max_length': '100', 'db_index': 'True'})
        },
        'taggit.taggeditem': {
            'Meta': {'object_name': 'TaggedItem'},
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'taggit_taggeditem_tagged_items'", 'to': "orm['contenttypes.ContentType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'object_id': ('django.db.models.fields.IntegerField', [], {'db_index': 'True'}),
            'tag': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'taggit_taggeditem_items'", 'to': "orm['taggit.Tag']"})
        }
    }

    complete_apps = ['accounts']

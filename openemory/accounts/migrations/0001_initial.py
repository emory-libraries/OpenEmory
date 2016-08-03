# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import taggit.managers
import openemory.accounts.fields
from django.conf import settings
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('taggit', '0002_auto_20150616_2121'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EsdPerson',
            fields=[
                ('_id', models.AutoField(serialize=False, editable=False, primary_key=True, db_column=b'prsn_i')),
                ('ppid', models.CharField(help_text=b'public person id/directory key', max_length=8, db_column=b'prsn_i_pblc')),
                ('directory_name', models.CharField(help_text=b'full name in the online directory', max_length=75, db_column=b'prsn_n_full_dtry')),
                ('ad_name', models.CharField(help_text=b'name in Active Directory', max_length=75, db_column=b'prsn_n_dspl_acdr')),
                ('firstmid_name', models.CharField(help_text=b'first and middle name in the online directory', max_length=20, db_column=b'prsn_n_fm_dtry')),
                ('last_name', models.CharField(help_text=b'last name in the online directory', max_length=25, db_column=b'prsn_n_last_dtry')),
                ('name_suffix', models.CharField(help_text=b'honorary or other name suffix in the online directory', max_length=15, db_column=b'prsn_n_sufx_dtry')),
                ('title', models.CharField(help_text=b'position title in the online directory', max_length=70, db_column=b'prsn_e_titl_dtry')),
                ('phone', models.CharField(help_text=b'phone number in the online directory', max_length=12, db_column=b'prad_a_tlph_empe_fmtt')),
                ('fax', models.CharField(help_text=b'fax number in the online directory', max_length=12, db_column=b'prad_a_fax_empe_fmtt')),
                ('department_id', models.CharField(help_text=b'identifying code of the department the user works in', max_length=10, db_column=b'dprt_c')),
                ('department_name', models.CharField(help_text=b'human-readable name of the department the user works in', max_length=40, db_column=b'dprt8dtry_n')),
                ('division_code', models.CharField(help_text=b'identifying code of the division the user works in', max_length=10, db_column=b'dvsn_i')),
                ('division_name', models.CharField(help_text=b'human-readable name of the division the user works in', max_length=40, db_column=b'dvsn8dtry_n')),
                ('mailstop_code', models.CharField(help_text=b"identifying code of the user's mailstop", max_length=12, db_column=b'mlst_i')),
                ('mailstop_name', models.CharField(help_text=b"human-readable name of the user's mailstop", max_length=30, db_column=b'mlst_n')),
                ('netid', models.CharField(help_text=b'network login', max_length=8, db_column=b'logn8ntwr_i')),
                ('internet_suppressed', openemory.accounts.fields.YesNoBooleanField(help_text=b"suppress user's directory information to off-campus clients", db_column=b'prsn_f_sprs_intt')),
                ('directory_suppressed', openemory.accounts.fields.YesNoBooleanField(help_text=b"suppress user's directory information to all clients", db_column=b'prsn_f_sprs_dtry')),
                ('information_suppressed', openemory.accounts.fields.YesNoBooleanField(help_text=b'no reference allowed to user', db_column=b'prsn_f_sprs_infr')),
                ('faculty_flag', openemory.accounts.fields.YesNoBooleanField(help_text=b'user is a faculty member', max_length=1, db_column=b'empe_f_fclt')),
                ('email', models.CharField(help_text=b"user's primary email address", max_length=100, db_column=b'emad_n')),
                ('email_forward', models.CharField(help_text=b'internal or external forwarding address for email', max_length=100, db_column=b'emad8frwd_n')),
                ('employee_status', models.CharField(max_length=1, db_column=b'emjo_c_stts_empe', choices=[(b'A', b'active'), (b'D', b'deceased'), (b'L', b'on leave'), (b'O', b'on-boarding'), (b'P', b'sponsored'), (b'T', b'terminated')])),
                ('person_type', models.CharField(max_length=1, db_column=b'prsn_c_type')),
            ],
            options={
                'db_table': '"esdv"."v_oem_fclt"',
                'managed': False,
                'db_tablespace': 'esdv',
            },
        ),
        migrations.CreateModel(
            name='Announcement',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('active', models.BooleanField(default=True)),
                ('message', models.TextField(max_length=500, validators=[django.core.validators.MaxLengthValidator(500)])),
                ('start', models.DateTimeField(null=True, blank=True)),
                ('end', models.DateTimeField(null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Bookmark',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('pid', models.CharField(max_length=255)),
                ('tags', taggit.managers.TaggableManager(to='taggit.Tag', through='taggit.TaggedItem', help_text='A comma-separated list of tags.', verbose_name='Tags')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Degree',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=30, verbose_name=b'Degree Name')),
                ('institution', models.CharField(help_text=b'Institution that granted the degree', max_length=255)),
                ('year', models.IntegerField(default=None, null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='ExternalLink',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=255)),
                ('url', models.URLField()),
            ],
        ),
        migrations.CreateModel(
            name='Grant',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=250, blank=True)),
                ('grantor', models.CharField(max_length=250, blank=True)),
                ('project_title', models.CharField(max_length=250, blank=True)),
                ('year', models.IntegerField(default=None, null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Position',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=200, verbose_name=b'Position Name')),
            ],
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('phone', models.CharField(max_length=50, blank=True)),
                ('dept_num', models.CharField(max_length=50, blank=True)),
                ('full_name', models.CharField(max_length=100, blank=True)),
                ('title', models.CharField(max_length=100, blank=True)),
                ('employee_num', models.CharField(max_length=50, blank=True)),
                ('subdept_code', models.CharField(max_length=50, blank=True)),
                ('hr_id', models.CharField(max_length=50, blank=True)),
                ('show_suppressed', models.BooleanField(default=False, help_text=b'Show information even if directory or internet suppressed')),
                ('nonfaculty_profile', models.BooleanField(default=False, help_text=b'User is allowed to have a profile even if they are non-faculty')),
                ('photo', models.ImageField(default=b'', upload_to=b'profile-photos/%Y/%m/', blank=True)),
                ('biography', models.TextField(default=b'', help_text=b'Biographical paragraph for public profile', blank=True)),
                ('research_interests', taggit.managers.TaggableManager(to='taggit.Tag', through='taggit.TaggedItem', blank=True, help_text=b'Comma-separated list of public research interests', verbose_name=b'Research Interests')),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['user__username'],
            },
        ),
        migrations.AddField(
            model_name='position',
            name='holder',
            field=models.ForeignKey(verbose_name=b'Position holder', to='accounts.UserProfile'),
        ),
        migrations.AddField(
            model_name='grant',
            name='grantee',
            field=models.ForeignKey(to='accounts.UserProfile'),
        ),
        migrations.AddField(
            model_name='externallink',
            name='holder',
            field=models.ForeignKey(to='accounts.UserProfile'),
        ),
        migrations.AddField(
            model_name='degree',
            name='holder',
            field=models.ForeignKey(verbose_name=b'Degree holder', to='accounts.UserProfile'),
        ),
    ]

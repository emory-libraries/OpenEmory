# file openemory/accounts/backends.py
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

from django.contrib.auth.models import User
from django.db.models import Q
from django_auth_ldap.backend import LDAPBackend as EmoryLDAPBackend

from openemory.accounts.models import EsdPerson, UserProfile

class FacultyOrLocalAdminBackend(EmoryLDAPBackend):
    '''Customized authentication backend based on
    :class:`~eullocal.django.emory_ldap.backends.EmoryLDAPBackend`.
    Only users who are designated as Faculty, in ESD or local users who
    are designated as superusers, Site Admins, or non-faculty with the
    nonfaculty_profile flag set are allowed to log in.
    '''

    def authenticate(self, username=None, password=None):
        # Only authenticate users who are flagged as faculty in ESD
        # or local accounts with superuser permission, 'Site Admin' role
        # or nonfaculty_flag set
        if self.USER_MODEL.objects.filter(username=username)\
               .filter(Q(is_superuser=True) | Q(groups__name='Site Admin') | \
                       Q(userprofile__nonfaculty_profile=True))\
               .exists() or \
               EsdPerson.faculty.filter(netid=username.upper()).exists():

            return super(FacultyOrLocalAdminBackend, self).authenticate(username=username,
                                                                password=password)

    # TODO: Django backends can optionally support per-object
    # permissions, which would probably make author-specific
    # permissions checks cleaner
    # 
    #  supports_object_permissions = True
    #
    # def has_perm(self, user, perm, obj=None):
    #  ...
    #  if obj is set and is an Article;
    #  check if user.username is in obj.owner list for author permissions
    #  (how to determine author permissions?)
    #
    # NOTE: to make this adding this may also require a small template filter
    # to allow passing an object to the has_perm method
    

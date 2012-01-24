from django.contrib.auth.models import User
from django.db.models import Q
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend

from openemory.accounts.models import EsdPerson, UserProfile

class FacultyOrLocalAdminBackend(EmoryLDAPBackend):
    '''Customized authentication backend based on
    :class:`~eullocal.django.emory_ldap.backends.EmoryLDAPBackend`.
    Only users who are designated as Faculty in ESD or local users who
    are designated as superusers or Site Admins are allowed to log in.
    '''    

    def authenticate(self, username=None, password=None):
        # Only authenticate users who are flagged as faculty in ESD
        # or local accounts with superuser permission
        if self.USER_MODEL.objects.filter(username=username)\
               .filter(Q(is_superuser=True) | Q(groups__name='Site Admin'))\
               .exists() or \
               EsdPerson.objects.filter(netid=username.upper(),
                                    person_type='F').exists() or \
               UserProfile.objects.filter(user=User.objects.filter(username=username)).\
               filter(Q(nonfaculty_profile=True)).exists():

            return super(FacultyOrLocalAdminBackend, self).authenticate(username=username,
                                                                password=password)
        

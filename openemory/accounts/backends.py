from django.db.models import Q
from eullocal.django.emory_ldap.backends import EmoryLDAPBackend

from openemory.accounts.models import EsdPerson

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
                                    person_type='F').exists():

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
    

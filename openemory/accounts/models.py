from django.contrib.auth.models import User
from django.db import models
from eullocal.django.emory_ldap.models import AbstractEmoryLDAPUserProfile
from taggit.managers import TaggableManager
from taggit.models import TaggedItem


class UserProfile(AbstractEmoryLDAPUserProfile):
    user = models.OneToOneField(User)
    research_interests = TaggableManager()


def researchers_by_interest(interest):
    # filtering on userprofile__research_interests__name fails, but
    # this seems to work correctly
    return User.objects.filter(userprofile__tagged_items__tag__name=interest)

from django.contrib.auth.models import User
from django.db import models
from eullocal.django.emory_ldap.models import AbstractEmoryLDAPUserProfile
from taggit.managers import TaggableManager


class UserProfile(AbstractEmoryLDAPUserProfile):
    user = models.OneToOneField(User)
    research_interests = TaggableManager()

def _create_profile(sender, instance, created, **kwargs):
    # create profile if this is a new User being created OR
    # if profile does not yet exist
    if created or not UserProfile.objects.filter(user=instance).exists():
        profile = UserProfile(user=instance)
        profile.save()
models.signals.post_save.connect(_create_profile, sender=User)


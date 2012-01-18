from django import forms
from taggit.forms import TagField

from openemory.accounts.models import UserProfile

class TagForm(forms.Form):
    # super-simple tag edit form with one tag field
    tags = TagField()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('research_interests', 'show_suppressed')

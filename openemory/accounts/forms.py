from django import forms
from django.forms.models import inlineformset_factory
from django.utils.translation import ugettext_lazy as _
from taggit.forms import TagField

from openemory.accounts.models import UserProfile, Degree, Position, Grant
from openemory.inlinemodelformsets import ModelForm

class TagForm(forms.Form):
    # super-simple tag edit form with one tag field
    tags = TagField()


DegreeFormSet = inlineformset_factory(UserProfile, Degree, extra=1)
PositionFormSet = inlineformset_factory(UserProfile, Position, extra=1)
GrantFormSet = inlineformset_factory(UserProfile, Grant, extra=1)

class ProfileForm(ModelForm):
    error_css_class = 'error'
    required_css_class = 'required'
    # NOTE: there doesn't seem to be a way to pass css classes to
    # formsets; this will probably need to be handled in the template
    
    class Meta:
        model = UserProfile
        fields = ('research_interests', 'show_suppressed', 'photo',
                  'biography')
        # TODO: Django 1.3 defaults to a new ClearableFileInput for file
        # fields. unfortunately it's harder to style. Using FileInput for
        # now, though it would be nice to switch back to Clearable later.
        widgets = {'photo': forms.FileInput}
        
    class Forms:
        inlines = {
            'degrees': DegreeFormSet,
            'positions': PositionFormSet,
# TODO: contracted design does not include grants. add them back.
#            'grants': GrantFormSet,
        }


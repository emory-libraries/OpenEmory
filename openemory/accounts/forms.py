from django import forms
from django.forms.models import inlineformset_factory
from taggit.forms import TagField

from openemory.accounts.models import UserProfile, Degree, Position, Grant
from openemory.inlinemodelformsets import ModelForm

class TagForm(forms.Form):
    # super-simple tag edit form with one tag field
    tags = TagField()


DegreeFormSet = inlineformset_factory(UserProfile, Degree)
PositionFormSet = inlineformset_factory(UserProfile, Position)
GrantFormSet = inlineformset_factory(UserProfile, Grant)

class ProfileForm(ModelForm):
    error_css_class = 'error'
    required_css_class = 'required'
    # NOTE: there doesn't seem to be a way to pass css classes to
    # formsets; this will probably need to be handled in the template
    
    class Meta:
        model = UserProfile
        fields = ('research_interests', 'show_suppressed', 'photo',
                  'biography')
        
    class Forms:
        inlines = {
            'degrees': DegreeFormSet,
            'positions': PositionFormSet,
            'grants': GrantFormSet,
        }


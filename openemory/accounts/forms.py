from django import forms
from django.forms.models import inlineformset_factory
from django.utils.translation import ugettext_lazy as _
from taggit.forms import TagField

from openemory.accounts.models import UserProfile, Degree, Position, Grant
from openemory.inlinemodelformsets import ModelForm

class TagForm(forms.Form):
    # super-simple tag edit form with one tag field
    tags = TagField()


class DegreeForm(ModelForm):
    class Meta:
        model = Degree
        widgets = {
            'name': forms.TextInput(attrs={'class': 'text degree-name', 'size': 20}),
            'institution': forms.TextInput(attrs={'class': 'text', 'size': 19}),
            'year': forms.TextInput(attrs={'class': 'text', 'size': 4})
        }

    def __init__(self, *args, **kwargs):
        # if no instance, set initial values for use as labels
        if 'initial' not in kwargs and 'instance' not in kwargs:
            initial = {'name': 'degree', 'institution': 'institution',
                       'year': 'year'}
            kwargs['initial'] = initial
        super(DegreeForm, self).__init__(*args, **kwargs)

DegreeFormSet = inlineformset_factory(UserProfile, Degree, extra=1, form=DegreeForm)
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
        
    class Forms:
        inlines = {
            'degrees': DegreeFormSet,
            'positions': PositionFormSet,
# TODO: contracted design does not include grants. add them back.
#            'grants': GrantFormSet,
        }


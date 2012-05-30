import logging
from django import forms
from django.forms.formsets import formset_factory
from django.forms.models import inlineformset_factory
from django.utils.translation import ugettext_lazy as _
from taggit.forms import TagField

from openemory.accounts.models import UserProfile, Degree, Position, Grant
from openemory.inlinemodelformsets import ModelForm
from openemory.util import solr_interface

logger = logging.getLogger(__name__)

help_text= {'name':'degree', 'institution': 'institution', 'year': 'year'}
class DegreeForm(ModelForm):
    error_css_class = 'error'
    required_css_class = 'required'

    name = forms.CharField(error_messages={'required':
                                           'Degree name is required to add a degree.'},
                           widget=forms.TextInput(attrs={'class': 'text degree-name',
                                           'size': 20, 'help_text': help_text['name'],
                                           'placeholder': 'degree'}))
    institution = forms.CharField(error_messages={'required':
                                                  'Institution is required to add a degree'},
                                  widget=forms.TextInput(attrs={'class': 'text',
                                                  'size': 19,
                                                  'help_text': help_text['institution'],
                                                  'placeholder': 'institution'}))
                                  
    class Meta:
        model = Degree
        widgets = {
            'year': forms.TextInput(attrs={'class': 'text', 'size': 4,
                                           'help_text': help_text['year'],
                                           'placeholder': 'year'})
        }


class PositionForm(ModelForm):
    error_css_class = 'error'
    required_css_class = 'required'

    class Meta:
        model = Position


class InterestForm(forms.Form):
    interest = forms.CharField()


DegreeFormSet = inlineformset_factory(UserProfile, Degree, extra=1, form=DegreeForm)
PositionFormSet = inlineformset_factory(UserProfile, Position, extra=1, form=PositionForm)
GrantFormSet = inlineformset_factory(UserProfile, Grant, extra=1)
InterestFormSet = formset_factory(InterestForm, extra=1, can_delete=True)

class ProfileForm(ModelForm):
    error_css_class = 'error'
    required_css_class = 'required'
    # NOTE: there doesn't seem to be a way to pass css classes to
    # formsets; this will probably need to be handled in the template
    delete_photo = forms.BooleanField(label='Remove this photo',
                                      required=False)
    
    class Meta:
        model = UserProfile
        fields = ('show_suppressed', 'photo', 'biography')
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

    def save(self, *args, **kwargs):
        if self.cleaned_data.get('delete_photo', False):
            # save=False because we're in the middle of save, and that would
            # probably cause this to go recursive or the world to implode or
            # something.
            self.instance.photo.delete(save=False)

        return super(ProfileForm, self).save(*args, **kwargs)


class FeedbackForm(forms.Form):
    error_css_class = 'error'
    required_css_class = 'required'

    name = forms.CharField(required=True, label='Your name',
                           widget=forms.TextInput(attrs={'class': 'text'}))
    email = forms.EmailField(required=True, label='Email',
                           widget=forms.TextInput(attrs={'class': 'text'}))
    subject = forms.CharField(required=False, label='Subject line',
                           widget=forms.TextInput(attrs={'class': 'text'}))
    phone = forms.CharField(required=False, label='Phone number',
                           widget=forms.TextInput(attrs={'class': 'text'}))
    message = forms.CharField(required=True, label='Message',
                           widget=forms.Textarea)

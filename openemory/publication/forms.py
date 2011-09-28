from django import forms

from eulxml.forms import XmlObjectForm
from eulxml.xmlmap.dc import DublinCore

class UploadForm(forms.Form):
    'Single-file upload form.'
    pdf = forms.FileField(label='')


#May want to move this to someplace like common
class ReadOnlyInput(forms.TextInput):
    '''Customized version of :class:`~django.forms.TextInput` to act as
    a read-only form field.'''
    def __init__(self, *args, **kwargs):
        readonly_attrs = {
            'readonly':'readonly',
            'class': 'readonly',
            'tabindex': '-1'
            }
        if 'attrs' in kwargs:
            kwargs['attrs'].update(readonly_attrs)
        else:
            kwargs['attrs'] = readonly_attrs
        super(ReadOnlyInput, self).__init__(*args, **kwargs)


class DublinCoreEditForm(XmlObjectForm):
    """Form to edit Dublin Core metadata for a
    :class:`~openemory.publication.models.Article`."""

    # make title required
    title = forms.CharField(required=True)
    # configure dc:type as a choice field populated by DCMI type vocabulary
    _type_choices = [(t, t) for t in DublinCore().dcmi_types]
    # add a blank value first so there is no default value
    _type_choices.insert(0, (None, '')) 
    type = forms.ChoiceField(choices=_type_choices, required=False)

    class Meta:
        model = DublinCore
        fields = ['title', 'description', 'creator_list', 'contributor_list',
                  'date', 'language', 'publisher',
                  'rights', 'source', 'subject_list', 'type',
                  'format', 'identifier'] 
        widgets = {
            'description': forms.Textarea,
            'format':  ReadOnlyInput,
            'identifier': ReadOnlyInput,
        }


class BasicSearchForm(forms.Form):
    'single-input article text search form'
    keyword = forms.CharField()

from django import forms

from eulxml.forms import XmlObjectForm, SubformField
from eulxml.xmlmap.dc import DublinCore
from eulxml.xmlmap import mods

from openemory.publication.models import ArticleMods, \
     Keyword, AuthorNote, FundingGroup, JournalMods

class UploadForm(forms.Form):
    'Single-file upload form.'
    pdf = forms.FileField(label='')

class BasicSearchForm(forms.Form):
    'single-input article text search form'
    keyword = forms.CharField()


## forms& subforms for editing article mods

class ArticleModsTitleEditForm(XmlObjectForm):
    form_label = 'Title Information'
    subtitle = forms.CharField(required=False)
    part_number = forms.CharField(required=False)
    part_name = forms.CharField(required=False)
    class Meta:
        model = mods.TitleInfo
        fields = ['title', 'subtitle', 'part_number', 'part_name']

class PartDetailNumberEditForm(XmlObjectForm):
    # part-detail form for number only - no label, not required
    number = forms.CharField(label='', required=False)
    class Meta:
        model = mods.PartDetail
        fields = ['number']

class PartExtentEditForm(XmlObjectForm):
    start = forms.CharField(required=False)
    end = forms.CharField(required=False)
    class Meta:
        model = mods.PartExtent
        fields = ['start', 'end']


class JournalEditForm(XmlObjectForm):
    form_label = 'Journal Information'
    volume = SubformField(formclass=PartDetailNumberEditForm)
    number = SubformField(formclass=PartDetailNumberEditForm)
    pages = SubformField(formclass=PartExtentEditForm)
    class Meta:
        model = JournalMods
        fields = ['title', 'publisher', 'volume', 'number',
                  'pages']

class FundingGroupEditForm(XmlObjectForm):
    form_label = 'Funding Group or Granting Agency'
    name = forms.CharField(label='', required=False) # suppress default label
    class Meta:
        model = FundingGroup
        fields = ['name']


class KeywordEditForm(XmlObjectForm):
    topic = forms.CharField(label='', required=False) # suppress default label
    class Meta:
        model = Keyword
        fields = ['topic']

class AbstractEditForm(XmlObjectForm):
    text = forms.CharField(label='',  # suppress default label
                           widget=forms.Textarea, required=False)
    class Meta:
        model = mods.Abstract
        fields = ['text']

class AuthorNotesEditForm(XmlObjectForm):
    text = forms.CharField(label='',  # suppress default label
                           widget=forms.Textarea, required=False)
    class Meta:
        model = AuthorNote
        fields = ['text']
    

class ArticleModsEditForm(XmlObjectForm):
    '''Form to edit the MODS descriptive metadata for an
    :class:`~openemory.publication.models.Article`.'''
    title_info = SubformField(formclass=ArticleModsTitleEditForm)
    funders = SubformField(formclass=FundingGroupEditForm)
    journal = SubformField(formclass=JournalEditForm)
    abstract = SubformField(formclass=AbstractEditForm)
    keywords = SubformField(formclass=KeywordEditForm)
    author_notes = SubformField(formclass=AuthorNotesEditForm)
    class Meta:
        model = ArticleMods
        fields = ['title_info', 'funders', 'journal', 'abstract', 'keywords',
                  'author_notes']

        


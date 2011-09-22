from django import forms
from taggit.forms import TagField

class TagForm(forms.Form):
    # super-simple tag edit form with one tag field
    tags = TagField()

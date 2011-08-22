from django import forms

class UploadForm(forms.Form):
    'Single-file upload form.'
    pdf = forms.FileField(label='')

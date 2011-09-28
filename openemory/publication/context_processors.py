from openemory.publication.forms import BasicSearchForm

def search_form(request):
    '''`Template context processor
    <https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors>`_
    to add a :class:`~openemory.publication.forms.BasicSearchForm` named
    ``ARTICLE_SEARCH_FORM`` to each page.'''
    return { 'ARTICLE_SEARCH_FORM': BasicSearchForm(auto_id='search-%s') }

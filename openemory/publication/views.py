from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import Http404
from django.shortcuts import render
from django.utils.safestring import mark_safe
from eulfedora.server import Repository
from eulfedora.util import RequestFailed
from eulfedora.views import raw_datastream

from eulcommon.djangoextras.http import HttpResponseSeeOtherRedirect
from openemory.accounts.auth import login_required
from openemory.publication.forms import UploadForm
from openemory.publication.models import Article
from openemory.util import md5sum


@login_required
def upload(request):
    '''Upload a file and ingest an
    :class:`~openemory.publication.models.Article` object into the
    repository.  On GET, displays the upload form.  On POST with a
    vaild file, ingests the content into Fedora.
    '''
    context = {}
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            # init repo with request to use logged-in user credentials for fedora access
            repo = Repository(request=request) 
            obj = repo.get_object(type=Article)
            uploaded_file = request.FILES['pdf']
            # use filename as preliminary title
            obj.label = uploaded_file.name
            # copy object label into dc:title
            obj.dc.content.title = obj.label
            # set the username of the currently-logged in user as object owner
            obj.owner = request.user.username
            # set uploaded file as pdf datastream content
            obj.pdf.content = uploaded_file
            # for now, use the content type passed by the browser (even though we know it is unreliable)
            # eventually, we'll want to use mime magic to inspect files before ingest
            obj.pdf.mimetype = uploaded_file.content_type 
            obj.dc.content.format = obj.pdf.mimetype
            # calculate MD5 checksum for the uploaded file before ingest
            obj.pdf.checksum = md5sum(uploaded_file.temporary_file_path())
            obj.pdf.checksum_type = 'MD5'
            try:
                saved = obj.save('upload via OpenEmory')
                if saved:
                    messages.success(request,
                        'Successfully uploaded article PDF <%(tag)s>%(file)s</%(tag)s>; saved as <%(tag)s>%(pid)s</%(tag)s>' \
                                     % {'file': uploaded_file.name, 'pid': obj.pid, 'tag': 'strong'})
                    return HttpResponseSeeOtherRedirect(reverse('site-index'))
            except RequestFailed as rf:
                context['error'] = rf
            
    else:
        # init unbound form for display
        form = UploadForm()
        
    context['form'] = form

    return render(request, 'publication/upload.html', context)

def download_pdf(request, pid):
    '''View to allow access the PDF datastream of a
    :class:`openemory.publication.models.Article` object.  Sets a
    content-disposition header that will prompt the file to be saved
    with a default title based on the object label.
    '''
    repo = Repository(request=request)
    try:
        # retrieve the object so we can use it to set the download filename
        obj = repo.get_object(pid, type=Article)
        extra_headers = {
            # generate a default filename based on the object
            # FIXME: what do we actually want here? ARK noid?
            'Content-Disposition': "attachment; filename=%s.pdf" % obj.pid
        }
        # use generic raw datastream view from eulfedora
        return raw_datastream(request, pid, Article.pdf.id, type=Article,
                              repo=repo, headers=extra_headers)
    except RequestFailed:
        raise Http404




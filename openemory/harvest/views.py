from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods

from openemory.accounts.auth import permission_required
from openemory.harvest.models import HarvestRecord

@permission_required('harvest.view_harvestrecord')
def queue(request):
    '''Display the queue of harvested records. '''

    # for now, return all records - no pagination, etc.
    # - restrict to only harvested records (which can be ingested or ignored)
    records = HarvestRecord.objects.filter(status='harvested').order_by('harvested').all()
    
    template_name = 'harvest/queue.html'
    # for ajax requests, only display the inner content
    if request.is_ajax():
        template_name = 'harvest/snippets/queue.html'
    return render(request, template_name, {'records': records})

@require_http_methods(['DELETE'])
@permission_required('harvest.ignore_harvestrecord') 
def record(request, id):
    '''View for a single
    :class:`~openemory.harvest.models.HarvestRecord`.  Currently only
    supports HTTP DELETE.

    On DELETE, marks the record as ``ignored`` (i.e., will not be
    ingested into the repository).
    '''
    record = get_object_or_404(HarvestRecord, pk=id)
    if request.method == 'DELETE':
        # set the specified record to ignored
        record.mark_ignored()
        # return a 200 Ok response on success
        return HttpResponse('Record ignored', mimetype='text/plain')

        

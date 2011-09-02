from django.shortcuts import render

from openemory.accounts.auth import permission_required

@permission_required('harvest.view_harvestrecord')
def queue(request):
    '''Display the queue of harvested records. '''
    return render(request, 'harvest/queue.html')

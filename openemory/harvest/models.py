from django.db import models
from openemory.harvest.entrez import EntrezClient

class HarvestRecord(models.Model):
    # place-holder db model for now, for permissions hook
    class Meta:
        permissions = (
            # add, change, delete are avilable by default
            ('view_harvestrecord', 'Can see available harvested records'),
        )


# TODO: This doesn't feel like a "model" per se, but not sure precisely
# where else it belongs...
class OpenEmoryEntrezClient(EntrezClient):
    def get_emory_articles(self):
        return self.esearch(
            db='pmc',     # search PubMed Central
            term='emory', # for the term "emory"
            field='affl', # in the "Affiliation" field
        )

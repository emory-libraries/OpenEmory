from django.db import models

class HarvestRecord(models.Model):
    # place-holder db model for now, for permissions hook
    class Meta:
        permissions = (
            # add, change, delete are avilable by default
            ('view_harvestrecord', 'Can see available harvested records'),
        )


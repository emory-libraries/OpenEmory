class EsdRouter(object):
    '''A `database router <https://docs.djangoproject.com/en/dev/topics/db/multi-db/>`_
    to divert :class:`~openemory.accounts.models.EsdPerson` objects to the
    ``esd`` database.'''

    def esd_model(self, model):
        return model._meta.app_label == 'accounts' and \
            model._meta.object_name == 'EsdPerson'

    def db_for_read(self, model, **hints):
        '''Read :class:`~openemory.accounts.models.EsdPerson` objects from
        the ``esd`` database.'''
        if self.esd_model(model):
            return 'esd'
        # otherwise no opinion

    def db_for_write(self, model, **hints):
        '''Write :class:`~openemory.accounts.models.EsdPerson` objects to
        the ``esd`` database.'''
        if self.esd_model(model):
            return 'esd'

    def allow_syncdb(self, db, model):
        '''Sync :class:`~openemory.accounts.models.EsdPerson` objects to the
        ``esd`` database.'''
        # sync EsdPerson to esd
        if db == 'esd' and self.esd_model(model):
            return True
        # don't sync anything else to esd or EsdPerson to any other db
        if db == 'esd' or self.esd_model(model):
            return False
        # no opinion on any other combinations

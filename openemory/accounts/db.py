# file openemory/accounts/db.py
# 
#   Copyright 2010 Emory University General Library
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

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

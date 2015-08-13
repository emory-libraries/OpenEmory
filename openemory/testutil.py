# file openemory/testutil.py
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

from django.conf import settings
from eulfedora import testutil
from nose.plugins import Plugin
import os
from django.db.models.loading import get_models


try:
    import xmlrunner
    settings.TEST_OUTPUT_DIR='test-results'
except ImportError:
    pass

# http://www.caktusgroup.com/blog/2010/09/24/simplifying-the-testing-of-unmanaged-database-models-in-django/
# class ManagedModelTestRunner(TestRunner):
#     """
#     Test runner that automatically makes all unmanaged models in your Django
#     project managed for the duration of the test run, so that one doesn't need
#     to execute the SQL manually to create them.
#     """




class UnManagedModels(Plugin):

    def options(self, parser, env=os.environ):
        super(UnManagedModels, self).options(parser, env=env)

    def configure(self, options, conf):
        self.unmanaged_models = [m for m in get_models()
                                 if not m._meta.managed]
        for m in self.unmanaged_models:
            m._meta.managed = True

    def finalize(self, result):
        # reset unmanaged models
        for m in self.unmanaged_models:
            m._meta.managed = False

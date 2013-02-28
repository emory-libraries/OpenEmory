# file openemory/accounts/fields.py
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

from django.db import models

class YesNoBooleanField(models.BooleanField):
    '''A Field that stores Boolean values as characher values 'Y' and
    'N'.'''
    # It seems an odd way to store it, really, but we need data from a
    # read-only db that does it that way.

    __metaclass__ = models.SubfieldBase

    def db_type(self, *args, **kwargs):
        return 'char(1)'

    def to_python(self, value):
        if isinstance(value, bool) or value is None:
            return value
        return not (value == 'N')

    def get_prep_value(self, value):
        if value is None:
            return value
        return 'Y' if value else 'N'

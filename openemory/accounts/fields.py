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

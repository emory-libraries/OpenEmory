"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""
import datetime

from django.test import TestCase
from downtime.models import Period
from .models import Banner

class BannerTest(TestCase):
    def test_is_active(self):
        """
        Tests the banner will be visible when the date range is applicable
        """
        self.p1 = Period.objects.create(
            id=123,
            start_time = datetime.datetime.now(),
            end_time = datetime.datetime.now() + datetime.timedelta(days=1)
        )
        self.b1 = Banner.objects.create(
            id=1234,
            message = "Test banner",
            period = self.p1,
            days=0
        )

        self.assertEqual(self.b1.period, self.p1 )

        # Banner should be active initally
        self.assertTrue(self.b1.is_active, "Banner should be active")

        # Change Period start_time to tomorrow
        self.p1.start_time = datetime.datetime.now() + datetime.timedelta(days=1)
        self.p1.save();

        # Banner should be inactive
        self.assertFalse(self.b1.is_active, "Banner should not be active")

        # Change Banner day range to 1 day out
        self.b1.days = 1

        # Banner should be active
        self.assertTrue(self.b1.is_active, "Banner should be active")

        # Set banner to disabled
        self.b1.disabled = True
        self.b1.save()

        # Banner should be inactive
        self.assertFalse(self.b1.is_active, "Banner should not be active if set to disabled.")

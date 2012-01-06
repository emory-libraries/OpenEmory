from django.conf import settings
from eulfedora import testutil

TestRunner = testutil.FedoraTextTestSuiteRunner

try:
    import xmlrunner
    TestRunner = testutil.FedoraXmlTestSuiteRunner
    settings.TEST_OUTPUT_DIR='test-results'
except ImportError:
    pass

# http://www.caktusgroup.com/blog/2010/09/24/simplifying-the-testing-of-unmanaged-database-models-in-django/
class ManagedModelTestRunner(TestRunner):
    """
    Test runner that automatically makes all unmanaged models in your Django
    project managed for the duration of the test run, so that one doesn't need
    to execute the SQL manually to create them.
    """
    def setup_test_environment(self, *args, **kwargs):
        from django.db.models.loading import get_models
        self.unmanaged_models = [m for m in get_models()
                                 if not m._meta.managed]
        for m in self.unmanaged_models:
            m._meta.managed = True
        super(ManagedModelTestRunner, self).setup_test_environment(*args,
                                                                   **kwargs)

    def teardown_test_environment(self, *args, **kwargs):
        super(ManagedModelTestRunner, self).teardown_test_environment(*args,
                                                                      **kwargs)
        # reset unmanaged models
        for m in self.unmanaged_models:
            m._meta.managed = False

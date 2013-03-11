Notes for developers
====================

The following instructions can be ignored when deploying to a staging
or production environment, but may be helpful to a developer working
on the project or running automated tests.

Session configuration
---------------------

By default, this project is configured to mark session cookies as secure. To
enable login over HTTP (e.g., when developing with Django's runserver), you
will need to override this in your ``localsettings.py``.  See the example
and comments in ``localsettings.py.dist``.

Test setup
----------

Certain unit tests pass test user credentials to Fedora, in order to test and
simulate accessing Fedora as the logged in user.  For tests to work properly,
the unit test user should be defined (with appropriate permissions)
as a fedora account.  See :mod:`openemory.publication.tests` for
account details.

Database support
----------------

The use of oracle tablespaces in the table name of
:class:`~openemory.accounts.models.EsdPerson` prevents the application from
working with a sqlite3 database. MySQL handles the unusual value as a table
name. If you must use sqlite3, simple change that class's ``db_table`` or
use the default value.

ESD database
------------

The test, staging, and development versions of the application access the
read-only Emory Shared Data oracle database. Due to security restrictions on
the database, it is only available from select machines. If your development
environment is not one of those machines (and it probably isn't), then set
up a MySQL database, and load a fixture with a small but carefully-selected
sample of real or realistic data::

   $ ./manage.py loaddata --database=esd esdpeople

Because this is a static database, multiple developers may work a
single copy of this fixture.  In this case, it is highly recommended
to configure a unique **TEST_NAME** for your esd database to avoid
database collisions when running unit tests.


PIDMan server
-------------

When developing locally, ``DEV_ENV`` should be set to True in
``localsettings.py``. This will cause PIDs to be generated using the
default method instead of using the PIDMan server if the PIDMAN
variables are not configured in ``localsettings.py``.


Tests, South, & fixtures
------------------------

:mod:`openemory` uses :mod:`south` to manage and db models, but due to
the multi-db setup with ESD, South migrations and tests must be
disabled when running unit tests (see settings for
``SKIP_SOUTH_TESTS`` and ``SOUTH_TESTS_MIGRATE`` in ``settings.py``).

In particular, this means that any initial data or data fixtures
normally managed by :mod:`south` will **not** be automatically loaded
when running unit tests; such fixtures should be explicitly included
as test fixtures where they are required.

Sending Email
-------------

Django email configurations should not be needed in staging or production,
but to test sending emails on a development machine, you may need to add
settings for **EMAIL_HOST** and **SERVER_EMAIL**.


-----

Notes on included items
~~~~~~~~~~~~~~~~~~~~~~~

* `Add icon <http://www.veryicon.com/icons/system/on-stage/symbol-add.html>`_, free
  for private & commercial use (not allowed to sell or redistribute).
* `Tag icon <http://www.veryicon.com/icons/internet--web/web-development-2/tag-sharp.html>`_
  free for use; Creative Commons attribution 3.0 license.
* jQuery "dirty form" plugin (GPL/MIT)
  http://plugins.jquery.com/project/dirtyform
  https://github.com/acvwilson/dirty_form
* `Inline formset handling for ModelForm from django snippets
  <http://djangosnippets.org/snippets/2248/>`_ added as
  `openemory.inlinemodelformsets`.  BSD license.
* Creative Commons license icons downloaded from
  http://creativecommons.org/about/downloads.  Per Creative Commons
  policies, these icons may only be used to point to the appropriate
  license; see http://creativecommons.org/policies for more information.
* `django-dynamic-formset jQuery plugin <http://code.google.com/p/django-dynamic-formset/>`_
  New BSD license.
* `livequery <https://github.com/brandonaaron/livequery>`_ (needed for dynamic dirtyform),
  MIT license
* `XML icon <http://www.iconarchive.com/show/adobe-cs4-icons-by-deleket/File-Adobe-Dreamweaver-XML-01-icon.html>`_ (for xml admin links),
   CC attribution/non-commercial/no-derivative



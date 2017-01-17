.. _DEPLOYNOTES:

Installation
============

Software dependencies
---------------------

We recommend the use of `pip <http://pip.openplans.org/>`_ and `virtualenv
<http://virtualenv.openplans.org/>`_ for environment and dependency management
in this and other Python projects. If you don't have them installed we
recommend ``sudo easy_install pip`` and then ``sudo pip install virtualenv``.

Bootstrapping a development environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Copy ``openemory/localsettings.py.dist`` to ``openemory/localsettings.py``
  and configure any local settings: **DATABASES**,  **SECRET_KEY**,
  **SOLR_**, **FEDORA_**,  customize **LOGGING**, etc.
* Create a new virtualenv and activate it.
* Install fabric: ``pip install fabric``
* Use fabric to run a local build, which will install python dependencies in
  your virtualenv, run unit tests, and build sphinx documentation: ``fab build``

Deploy to QA and Production should be done using ``fab deploy``.

After configuring your database, run syncdb::

    python manage.py syncdb

Use eulindexer to index repository content into your configured Solr instance.


Configure the environment
~~~~~~~~~~~~~~~~~~~~~~~~~

When first installing this project, you'll need to create a virtual environment
for it. The environment is just a directory. You can store it anywhere you
like; in this documentation it'll live right next to the source. For instance,
if the source is in ``/home/httpd/openemory/src``, consider creating an
environment in ``/home/httpd/openemory/env``. To create such an environment, su
into apache's user and::

  $ virtualenv --no-site-packages /home/httpd/openemory/env

This creates a new virtual environment in that directory. Source the activation
file to invoke the virtual environment (requires that you use the bash shell)::

  $ . /home/httpd/openemory/env/bin/activate

Once the environment has been activated inside a shell, Python programs
spawned from that shell will read their environment only from this
directory, not from the system-wide site packages. Installations will
correspondingly be installed into this environment.

.. Note::
  Installation instructions and upgrade notes below assume that
  you are already in an activated shell.

Install System Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Beginning with `Release 0.5 - Faculty Profiles`_, OpenEmory uses the
Python Imaging Library Pillow to support faculty profile photo uploads.
-Pillow can be installed via pip, but support for JPEG and PNG formats
depends on the certain system libraries.  For JPEG, libjpeg is
required; for PNG, libz is required.  On recent versions of Ubuntu,
libjpeg8-dev and zlib1g-dev packages should be installed
(libjpeg62-dev probably works with the path adjustment noted below).

.. _Python Imaging Library (Pillow): https://pypi.python.org/pypi/Pillow

.. Note::

  By default on Ubuntu, **libz.so** is not installed directly in
  ``/usr/lib``, but in an architecture-specific like
  ``/usr/lib/i386-linux-gnu/`` or ``/usr/lib/x86_64-linux-gnu``.  As a
  work-around, add a symlink either to ``/usr/lib`` or to the
  virtualenv ``lib`` directory, e.g.::

    $ sudo ln -s /usr/lib/i386-linux-gnu/libz.so /usr/lib

To test that the required libraries are installed correctly, ``pip
install PIL`` (or ``pip install --upgrade PIL`` if already installed).
At the end of the installation, PIL setup provides a summary of the
configuration.  Check to see that JPEG and PNG are listed as
available::

    --- JPEG support available
    --- ZLIB (PNG/ZIP) support available


`python-ldap` requires the following packages:  python-dev libldap2-dev libsasl2-dev libssl-dev


Install python dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~

OpenEmory depends on several python libraries. The installation is mostly
automated, and will print status messages as packages are installed. If there
are any errors, pip should announce them very loudly.

To install python dependencies, cd into the repository checkout and::

  $ pip install -r pip-install-req.txt

*Note*: installation of some dependencies (i.e. django-tracking) requires
that django settings are available. To install these manually, use this::

  $ env DJANGO_SETTINGS_MODULE=openemory.settings pip install -r pip-install-after-config.txt

If you are a developer or are installing to a continuous integration server
where you plan to run unit tests, code coverage reports, or build sphinx
documentation, you probably will also want to::

  $ pip install -r pip-dev-req.txt

After this step, your virtual environment should contain all of the
needed dependencies.

Solr/EULindexer
~~~~~~~~~~~~~~~

OpenEmory uses `Solr <http://lucene.apache.org/solr/>`_ and
:mod:`eulindexer` for searching and indexing Fedora content. The Solr schema
included with the source code at ``solr/schema.xml`` should be used as the
Solr schema configuration. For convenience, this directory also contains a
sample ``solrconfig.xml`` and minimal versions of all other solr
configuration files used by the index.

The url for accessing the configured Solr instance should be set in
``localsettings.py`` as **SOLR_SERVER_URL**.

Repository content accessible via OpenEmory should be indexed using
**EULindexer**.  To add OpenEmory to an installed and configured
instance of EULindexer, add the deployed indexdata url to the
eulindexer ``localsettings.py``, e.g.::

  INDEXER_SITE_URLS = {
      'openemory': 'http://openemory.library.emory.edu/indexdata/',
  }

To populate the index initially, or to reindex all content, run the
``reindex`` script that is available in EULindexer::

  $ python manage.py reindex -s openemory


Install the application
-----------------------

Apache
~~~~~~

After installing dependencies, copy and edit the wsgi and apache
configuration files in src/apache inside the source code checkout. Both may
require some tweaking for paths and other system details.

Configuration
~~~~~~~~~~~~~

Configure application settings by copying ``localsettings.py.dist`` to
``localsettings.py`` and editing for local settings (database, Fedora
repository, Pid Manager, etc.).

After configuring all settings, initialize the db with all needed
tables and initial data using::

  $ python manage.py syncdb
  $ python manage.py migrate

Load Fedora fixtures and control objects to the configured repository
using::

  $ python manage.py syncrepo

This application makes use of the :mod:`django.contrib.sites` module
to generate ARKs.  After running ``syncdb`` and starting the
web app, use the Django DB Admin site to configure the default site by
replacing the ``example.com`` domain with the domain for the deployed
web application.

Cron jobs
~~~~~~~~~

Session cleanup
^^^^^^^^^^^^^^^

The application uses database-backed sessions. Django recommends
periodically `clearing the session table <https://docs.djangoproject.com/en/1.3/topics/http/sessions/#clearing-the-session-table>`_
in this configuration. To do this, set up a cron job to run the following
command periodically from within the application's virtual environment::

  $ manage.py cleanup

This script removes any expired sessions from the database. We recommend
doing this about every week, though exact timing depends on usage patterns
and administrative discretion.

Index faculty
^^^^^^^^^^^^^

The application relies on current directory information about faculty. This
information is provided by Emory Shared Data, but we also index it in solr
for improved searching capabilities. Set up a nightly cron job to re-scan
the ESD data and update the index::

  $ manage.py index_faculty

Statistics email
^^^^^^^^^^^^^^^^

The application collects usage statistics and sends quarterly reports to
article authors. Set up a cron job to create and send these reports by
running the following command from within the application's virtual
environment. The script should run at the beginning of January, April, July,
and October::

  $ manage.py quarterly_stats_by_author

Harvest PMC Data
^^^^^^^^^^^^^^^^

The application harvests article metadata from PubMed Central nigtly and
stores it in the OpenEmory SQL database to be later ingested.
The followng command should be run to keep the harvest queue up to date.
In this mode article metadata is harvested from the last harvest date to the present::

  $ manage.py fetch_pmc_metadata --auto-date

Additionally, there is a second job which runs once a month that does a full harvest to catch
any records that may have been missed for any reason::

  $ manage.py fetch_pmc_metadata


Email Reports of Duplicates
^^^^^^^^^^^^^^^^^^^^^^^^^^^
Set up iWatch to trigger notifications on folder where reports are created.


Upgrade Notes
=============
Release 2.2.6 - OpenEmory Relaunch Interface Changes
----------------------------------------------------
* Please use the Django Admin to edit the flatpage contents in the database
  so that the site navigation can be updated. The "/about/authors-rights/" needs
  to be updated to "/about/author-rights/", title "Authors' Rights" needs to 
  be updated to "Author Rights".

Release 2.2.5 - OpenEmory Relaunch Interface Changes
----------------------------------------------------
* Please use the Django Admin to edit the flatpage contents in the database
  so that the site navigation can be updated. There needs to be
  "/about/depositadvice/" added, "/how-to/submit/" updated, and "/about/staff/"
  title updated.
* Please check the "django_flatpage_sites" table in the database and make sure
  that the "site_id" is all marked as "1" or the "site_id" that we are using
  for this app.
* Currently the Admin page may not be viewable due to a problem in eullocal;
  until it is fixed permanently, we just need to delete: `SiteProfileNotAvailable`
  from `/home/httpd/openemory/env/lib/python2.7/site-packages/eullocal/django/ldap/backends.py`.

Release 2.1.2 - Merging Old Preconnector
----------------------------------------
* fixing embargo duration
* pdf file download bug
* pubsid report
* download pmc subset

Release 2.1.1 - Author Enhancements
-----------------------------------
* fixing styles for publication page
* adjusting mods to save non emory faculty authors

Release 2.1.0 - Content Type Harmonization
------------------------------------------
* mime type debugging
* fixing styles

Release 2.0.0 - New Content Type (Presentation)
-----------------------------------------------
* adding new content

Release 1.9.0 - New Content Type (Poster)
-----------------------------------------
* adding new content

Release 1.8.0 - New Content Type (Report)
-----------------------------------------
* debugging conflicting policies in XACML

Release 1.7.0 - New Content Type (Conference)
---------------------------------------------


Release 1.6.0 - New Content Type (Chapter)
------------------------------------------
* run this script to cleanup journal articles (updated)

    $ python manage.py journal_title


Release 1.5.0 - New Content Type (Book)
---------------------------------------
* run this script to match all content models for articles and books

    $ python manage.py cmodel_cleanup

Release 1.4.0 - Author Enhancements
-----------------------------------
* run this script to match all current journal titles with Sherpa Romeo

    $ python manage.py journal_title

Release 1.3 - Pre Fedora Migration
----------------------------------
* run migrations for downtime

    $ python ./manage.py migrate downtime
    $ python ./manage.py migrate mx


Release 1.2.16 - Connector
--------------------------
* run migrations for publication

    $ python ./manage.py migrate publication

* create LastRun object::

    $ from openemory.publication.models import LastRun
    $ LastRun(name='Convert Symp to OE', start_time='2014-01-01 00:00:00').save()

* Set up iWatch to trigger notifications on folder where reports are created

* Setup cron job to run import command

* Configure ``REPORTS_DIR``  in localsettings.py


Release 1.2.10 - Symplectic Elements
------------------------------------
* run migrations for accounts to add add_articlerecord to Site Admin group permissions::

    $ python manage.py migrate accounts

* Add the following variables to localsettings.py::

    # SYMPLECTIC-Elements
    SYMPLECTIC_BASE_URL = <URL>
    SYMPLECTIC_USER = <USER>
    SYMPLECTIC_PASSWORD = <PASS>


Release 1.2.9 - Odds and Ends
-----------------------------
* Run migrations::

  $ python ./manage.py migrate accounts


Release 1.2.7 - OAI modifications
---------------------------------
* Run `add_dc_ident` to modify dc data::

  $ python ./manage.py add_dc_ident --username=<USERNAME>

* Run `add_to_oai` to update OAI info::

  $ python ./manage.py add_to_oai --username=<USERNAME>

Release 1.2.5 - Bug Fix
-----------------------
* The system pip and virtualenv packages need to be updated before the fab file is run::

  $ sudo pip install --upgrade pip
  $ sudo pip install --upgrade virtualenv

* Run `add_dc_ident` to restore dc identifiers::

  $ python ./manage.py add_dc_ident


Release 1.2.4 - Captcha / Bug Fixes
------------------------------------
* Add the following to local setting **BEFORE** fab is run. Values will be provided at deploy time::

    # reCAPTCHA keys for your server or domain from https://www.google.com/recaptcha/
    RECAPTCHA_PUBLIC_KEY = ''
    RECAPTCHA_PRIVATE_KEY = ''
    RECAPTCHA_OPTIONS = {}

Release 1.2.3 - OAI
-----------------------------------------------
* Run `syncrepo` to load collection object::

  $ python ./manage.py syncrepo


* A manage commnd needs to be run to prepare the articles to be harvested by OAI::

  $ python manage.py add_to_oai --username=<USERNAME> > oai.log


Release 1.2.2 - License and Rights Enhancements
-----------------------------------------------
* Run migrations to add License model::

  $ python ./manage.py migrate


* Run the following command to load the initial license info::

  $ python ./manage.py loaddata init_license


* A manage commnd needs to be run to remove empty contentMetadata datastreams, copy license info into the MODS and ADD OAI info.
  The script should be run with the ``fedoraAdmin`` user::


  $ python manage.py cleanup_articles --username=<USERNAME> > cleanup.log

Release 1.2 - Search Engine Optimization and bug fixes
------------------------------------------------------

* New configurations have been added ``localsettings.py``:

  * **GOOGLE_ANALYTICS_ENABLED** - set True/False to enable/disable Google
    Analytics on the site (analytics should generally only be enabled in
    production)

  * **GOOGLE_SITE_VERIFICATION** - set to the value provided by Google
    Webmaster Tools to allow site verification

  See  ``localsettings.py.dist`` for examples.


Release 1.0 - Design Integration, Rights and Technical Metadata
---------------------------------------------------------------
* Now using :mod:`django.contrib.flatpages` for pages with static site
  content (about, how-tos, etc).  Run ``syncdb`` and ``migrate`` to
  update the database::

   $ python manage.py syncdb
   $ python manage.py migrate

.. Note::

  For an existing installation with a database you want to preserve,
  you will have to fake the 0012_add_model_announcement migration
  if you receive the error message **Table accounts_announcement already exists**::

    $ python manage.py migrate accounts 0012 --fake --delete-ghost-migrations

  You can then run the ``migrate`` command above to finish the migrations.




* A nightly cron job is needed to run the following command to check for
  embargoes that have expired and reindex them so that the full text can be
  searched::

   $ python manage.py expire_embargo

  The output of this script should be redirected to a log.  The log
  Should be rolled on a regular basis.

* A nightly cron job is needed to sync indexed faculty data with ESD::

   $ python manage.py index_faculty

* A cron cron job is needed to run at the beginning of each quarter to send
  out stats for the previous quarter::

   $ python manage.py quarterly_stats_by_author

  The output of this script should be redirected to a log.  The log
  Should be rolled on a regular basis.


Release 0.7 - Polish & Prep
---------------------------

* ESD faculty information is now indexed in Solr for search
  functionality.  In order to accommodate indexing disparate types of
  data, the `unique key` for Solr has been changed.  Solr should be
  configured with the new schema, and then all data **must** be cleared
  and reindexed.
* Restart eulindexer after this and any other solr schema changes.
* After updating Solr with the new schema, index Faculty data from
  Emory Shared Data into Solr::

    $ python manage.py index_faculty

* This release adds models and migrations. Sync and migrate the database::

    $ python manage.py syncdb
    $ python manage.py migrate


Release 0.6 - Faculty Demo
--------------------------

* Now makes use the PID manager and the :mod:`django.contrib.sites`
  module to generate ARKs for repository content.  To configure:

  * After running ``syncdb`` and starting the web app, use the Django
    DB Admin site to configure the default site by replacing the
    ``example.com`` domain with the domain for the deployed web
    application.
  * Create a domain and user for OpenEmory ARKs on the PID manager
    (the user should have permissions to create pids and targets), and
    configure all of the **PIDMAN_** settings in ``localsettings.py``
    based on the examples in ``localsettings.py.dist``

Release 0.5 - Faculty Profiles
------------------------------

* Now includes :mod:`south` for database migrations.  For a new
  installation, you should run ``syncdb`` to add the required database
  tables for south and any of the other tables not managed by South::

   $ python manage.py syncdb

  .. Note::

     By default, Django will prompt you to create a superuser when you
     run ``syncdb`` on a new database; since the user profile model is
     managed by :mod:`south`, you should **not** attempt to create any
     accounts until after you have completed the migrations.  To skip
     this prompt, you may run ``syncdb`` with the ``--noinput``
     option.  After migrations are complete, use the
     ``createsuperuser`` manage.py command to create a new super ures.

  Then run the south ``migrate`` command to update the database
  tables that are now managed by :mod:`south`::

   $ python manage.py migrate

  For an existing installation with a database you want to preserve,
  run the ``syncdb`` step above to add the required database tables
  for south, and then fake the initial migrations::

   $ python manage.py migrate accounts 0001 --fake
   $ python manage.py migrate harvest 0001 --fake
   $ python manage.py migrate publication 0001 --fake

  After this step, you should be able to use South migrations
  normally.

* Python dependencies now include Python Imaging Library (PIL).  See
  `Install System Dependencies`_ for instructions on the libraries
  required for JPEG and PNG support.

* Profile editing provides an option for users to upload images; this
  user uploaded content will be stored in the configured
  **MEDIA_ROOT** directory.  System administrators may wish to revisit
  the configuration for this Django setting (previously set in
  ``settings.py`` but now included in ``localsettings.py``; see
  ``localsettings.py.dist`` for example configuration).


Release 0.4.x - Article Metadata
--------------------------------

* Run ``syncdb`` to add new article review permissions and update the
  **Site Admin** group permissions::

   $ python manage.py syncdb

* Added new logic for generating Article MODS from NLM records
  harvested from PubMed Central.  Any existing test records should
  either be removed and reharvested, or updated as follows.  Activate
  the virtualenv and start the Django console::

  $ python manage.py shell

  Then run the following to update Articles in the configured
  repository with NLM xml:

  .. code-block:: python

    from eulfedora.server import Repository
    from openemory.publication.models import Article
    from django.conf import settings
    repo = Repository(username=settings.FEDORA_MANAGEMENT_USER,
  	password=settings.FEDORA_MANAGEMENT_PASSWORD)
    for a in repo.get_objects_with_cmodel(Article.ARTICLE_CONTENT_MODEL, type=Article):
      if a.contentMetadata.exists:
        try:
          if unicode(a.contentMetadata.content):
            a.descMetadata.content = a.contentMetadata.content.as_article_mods()
            a.save('populating MODs from NLM xml')
        except:
          pass

* This release includes new solr fields. Configure a new core and reindex
  project content into it.

* This release includes support for editing inactive Fedora items. This
  support requires updated Fedora policies. Update Fedora policies while
  upgrading this package.

* Updated Fedora policies provide read access to all OpenEmory content
  (not published content only) to logged-in users with the "indexer"
  role.  It is recommended to create a Fedora user with an indexer
  role and configure :mod:`eulindexer` to use this account.  For
  example:

  .. code-block:: xml

    <user name="eulindexer" password="...">
      <attribute name="fedoraRole">
        <value>indexer</value>
      </attribute>
    </user>


Release 0.3.x - Searching & Social
----------------------------------

* This release includes new relational Python modules and database
  tables.  To upgrade, install new python dependencies in your
  virtualenv::

   $ pip install -r pip-install-req.txt

  And then update the database with new tables via ``syncdb``::

   $ python manage.py syncdb

  .. Note::

    As part of this release, the user profile model has been
    customized, which entails a database change.  If you wish to
    create profiles for existing Emory LDAP users, run the
    **inituser** script with the usernames. You may also want to drop
    the former ldap profile table,
    ``emory_ldap_emoryldapuserprofile``, as it is no longer in use.
    Any users created or updated after this upgrade will get the new
    profiles automatically.


Release 0.2.x - Harvesting
--------------------------

* This release includes new relational database tables and fixtures.
  Upgrade requires a ``syncdb``::

      $ python manage.py syncdb

* This release changes the project solr schema. Before installing the
  software, set up a new solr core for the project. The solr configuration
  files will be produced as part of the release. If the URL of this solr
  core is different from the old one then update it in
  ``localsettings.py``. After the updated OpenEmory website is live,
  reindex the site. As ``eulindexer``::

      $ python manage.py reindex -s openemory

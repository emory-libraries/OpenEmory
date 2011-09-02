import os
import re
import shutil
from fabric.api import abort, env, lcd, local, prefix, put, puts, require, \
                       run, sudo, task
from fabric.context_managers import cd, hide
from fabric.contrib import files
from fabric.contrib.console import confirm
from xml.etree.ElementTree import XML
import openemory

##
# automated build/test tasks
##

# omit these from the test coverage report
env.omit_coverage = ','.join([
    'openemory/manage.py',
    'openemory/settings.py',
    'openemory/localsettings.py',
    ])

def all_deps():
    '''Locally install all dependencies.'''
    local('pip install -r pip-install-req.txt -r pip-dev-req.txt')

def test():
    '''Locally run all tests.'''
    if os.path.exists('test-results'):
        shutil.rmtree('test-results')

    local('coverage run --branch openemory/manage.py test --noinput')
    local('coverage xml --include=openemory**/*.py --omit=%(omit_coverage)s' % env)

def doc():
    '''Locally build documentation.'''
    with lcd('doc'):
        local('make clean html')

@task
def build():
    '''Run a full local build/test cycle.'''
    all_deps()
    test()
    doc()


##
# deploy tasks
##

env.svn_rev_tag = ''
env.remote_path = '/home/httpd/sites/openemory'
env.remote_acct = 'openemory'
env.url_prefix = None

def configure(path=None, user=None, url_prefix=None, check_svn_head=True):
    'Configuration settings used internally for the build.'
    env.version = openemory.__version__
    config_from_svn(check_svn_head)
    # construct a unique build directory name based on software version and svn revision
    env.build_dir = 'openemory-%(version)s%(svn_rev_tag)s' % env
    env.tarball = 'openemory-%(version)s%(svn_rev_tag)s.tar.bz2' % env
    env.solr_tarball = 'openemory-solr-%(version)s%(svn_rev_tag)s.tar.bz2' % env

    if path:
        env.remote_path = path.rstrip('/')
    if user:
        env.remote_acct = user
    if url_prefix:
        env.url_prefix = url_prefix.rstrip('/')

def config_from_svn(check_svn_head=True):
    """Infer subversion location & revision from local svn checkout."""
    with hide('stdout'):
        svn_info = XML(local('svn info --xml', capture=True))
    env.svn_rev = svn_info.find('entry').get('revision')
    if openemory.__version_info__[-1]:
        env.svn_rev_tag = '-r' + env.svn_rev
    env.svn_url = svn_info.find('entry/url').text

    # using the local revision; ask confirmation if local checkout is
    # not at HEAD revision
    with hide('stdout'):
        head_svn_info = XML(local('svn info --xml %(svn_url)s' % env, capture=True))
    head_rev = head_svn_info.find('entry').get('revision')
    if check_svn_head and head_rev != env.svn_rev:
        if not confirm('Are you sure you want to deploy checked out svn revision %s (HEAD is %s)?' \
                       % (env.svn_rev, head_rev)):
            abort('Quitting')

def prep_source():
    'Checkout the code from svn and do local prep.'
    require('svn_url', 'svn_rev', 'build_dir',
            used_for='Checking out code from svn into build area')
    local('mkdir -p build')
    local('rm -rf build/%(build_dir)s' % env)
    local('svn export -r %(svn_rev)s %(svn_url)s build/%(build_dir)s' % env)
    # local settings handled remotely

    if env.url_prefix:
        env.apache_conf = 'build/%(build_dir)s/apache/openemory.conf' % env
        # back up the unmodified apache conf
        orig_conf = env.apache_conf + '.orig'
        local('cp %s %s' % (env.apache_conf, orig_conf))
        with open(orig_conf) as original:
            text = original.read()
        text = text.replace('WSGIScriptAlias / ', 'WSGIScriptAlias %(url_prefix)s ' % env)
        text = text.replace('Alias /static/ ', 'Alias %(url_prefix)s/static ' % env)
        text = text.replace('<Location />', '<Location %(url_prefix)s/>' % env)
        with open(env.apache_conf, 'w') as conf:
            conf.write(text)

    local('mkdir -p build/solr/openemory')
    local('rm -rf build/solr/openemory/conf')
    local('cp -a build/%(build_dir)s/solr build/solr/openemory/conf' % env)

def package_source():
    'Create a tarball of the source tree.'
    local('mkdir -p dist')
    local('tar cjf dist/%(tarball)s -C build %(build_dir)s' % env)
    local('tar cjf dist/%(solr_tarball)s -C build/solr openemory' % env)

def upload_source():
    'Copy the source tarball to the target server.'
    put('dist/%(tarball)s' % env,
        '/tmp/%(tarball)s' % env)

def extract_source():
    'Extract the remote source tarball under the configured remote directory.'
    with cd(env.remote_path):
        sudo('tar xjf /tmp/%(tarball)s' % env, user=env.remote_acct)
        # if the untar succeeded, remove the tarball
        run('rm /tmp/%(tarball)s' % env)
        # update apache.conf if necessary

def setup_virtualenv():
    'Create a virtualenv and install required packages on the remote server.'
    with cd('%(remote_path)s/%(build_dir)s' % env):
        # TODO: we should be using an http proxy here  (how?)
        # create the virtualenv under the build dir
        sudo('virtualenv --no-site-packages env',
             user=env.remote_acct)
        # activate the environment and install required packages
        with prefix('source env/bin/activate'):
            sudo('pip install -r pip-install-req.txt', user=env.remote_acct)

def configure_site():
    'Copy configuration files into the remote source tree.'
    with cd(env.remote_path):
        if not files.exists('localsettings.py'):
            abort('Configuration file is not in expected location: %(remote_path)s/localsettings.py' % env)
        sudo('cp localsettings.py %(build_dir)s/openemory/localsettings.py' % env,
             user=env.remote_acct)

    with cd('%(remote_path)s/%(build_dir)s' % env):
        with prefix('source env/bin/activate'):
            sudo('python openemory/manage.py collectstatic --noinput',
                 user=env.remote_acct)

def update_links():
    'Update current/previous symlinks on the remote server.'
    with cd(env.remote_path):
        if files.exists('current' % env):
            sudo('rm -f previous; mv current previous', user=env.remote_acct)
        sudo('ln -sf %(build_dir)s current' % env, user=env.remote_acct)

@task
def build_source_package(path=None, user=None, url_prefix='',
                         check_svn_head=True):
    '''Produce a tarball of the source tree and a solr core.'''
    # exposed as a task since this is as far as we can go for now with solr.
    # as solr deployment matures we should expose the most mature piece
    if isinstance(check_svn_head, basestring):
        # "False" and friends should be false. everything else default True
        check_svn_head = (check_svn_head.lower() not in
                          ('false', 'f', 'no', 'n', '0'))
    configure(path, user, url_prefix, check_svn_head)
    prep_source()
    package_source()

@task
def deploy(path=None, user=None, url_prefix=''):
    '''Deploy the web app to a remote server.'''

    build_source_package(path, user, url_prefix)
    upload_source()
    extract_source()
    setup_virtualenv()
    configure_site()
    update_links() 

@task
def revert(path=None, user=None):
    """Update remote symlinks to retore the previous version as current"""
    configure(path, user)
    # if there is a previous link, shift current to previous
    if files.exists('previous'):
        # remove the current link (but not actually removing code)
        sudo('rm current', user=env.remote_acct)
        # make previous link current
        sudo('mv previous current', user=env.remote_acct)
        sudo('readlink current', user=env.remote_acct)

@task
def clean():
    '''Remove build/dist artifacts generated by deploy task'''
    local('rm -rf build dist')
    # should we do any remote cleaning?

@task
def rm_old_builds(path=None, user=None, noinput=False):
    '''Remove old build directories on the deploy server.

    Takes the same path and user options as **deploy**.  By default,
    will ask user to confirm delition.  Use the noinput parameter to
    delete without requesting confirmation.
    '''
    configure(path, user)
    with cd(env.remote_path):
        with hide('stdout'):  # suppress ls/readlink output
            # get directory listing sorted by modification time (single-column for splitting)
            dir_listing = sudo('ls -t1', user=env.remote_acct)
            # get current and previous links so we don't remove either of them
            current = sudo('readlink current', user=env.remote_acct)
            previous = sudo('readlink previous', user=env.remote_acct)
            
        # split dir listing on newlines and strip whitespace
        dir_items = [n.strip() for n in dir_listing.split('\n')] 
        # regex based on how we generate the build directory:
        #   project name, numeric version, optional pre/dev suffix, optional revision #
        build_dir_regex = r'^openemory-[0-9.]+(-[A-Za-z0-9_-]+)?(-r[0-9]+)?$' % env
        build_dirs = [item for item in dir_items if re.match(build_dir_regex, item)]
        # by default, preserve the 3 most recent build dirs from deletion
        rm_dirs = build_dirs[3:]
        # if current or previous for some reason is not in the 3 most recent,
        # make sure we don't delete it
        for link in [current, previous]:
            if link in rm_dirs:
                rm_dirs.remove(link)

        if rm_dirs:
            for dir in rm_dirs:
                if noinput or confirm('Remove %s/%s ?' % (env.remote_path, dir)):
                    sudo('rm -rf %s' % dir, user=env.remote_acct)
        else:
            puts('No old build directories to remove')
 

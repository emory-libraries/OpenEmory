from openemory.settings import *
# Sphinx loads things in wonky order sometimes. Normally this shouldn't
# matter, but when it loads eullocal, tracking, and django admin all
# together, a mutual dependency appears between the
# eullocal.django.emory_ldap profile creation signal, tracking's urls
# self-check, and django admin's autodiscover. This dependency doesn't
# appear to happen when django loads things itself. It's pretty wacky. If we
# disable AUTH_PROFILE_MODULE just for docs, though, then emory_ldap doesn't
# create its signal, and the mutual dependency goes away.
AUTH_PROFILE_MODULE = None

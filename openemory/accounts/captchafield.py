# file django/forms/captchafield.py
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
'''
Django Form field & widget to make it easy to add reCAPTCHA to a Django form.
Projects that use this field should include the following settings in their
``settings.py``::
    RECAPTCHA_PUBLIC_KEY
    RECAPTCHA_PRIVATE_KEY
There is a remote_ip parameter used when submitting a captcha response to check
if it is valid.  It is recommended to pass this to any form that uses
:class:`ReCaptchaField` when you initialize the form with POSTed data, eg.::
    data = request.POST.copy()
    data['remote_ip'] = request.META['REMOTE_ADDR']
    form = EmailForm(data)
ReCaptcha options can be specified when initializing the Widget, e.g.::
    captcha = ReCaptchaField(widget=ReCaptchaWidget(attrs={'theme': 'blackglass'}))
You may also specify a RECAPTCHA_OPTIONS in your django settings.   Attributes
specified on an individual ReCaptchaWidget will take precedence over global
options specified in django settings.  Example usage::
    RECAPTCHA_OPTIONS = {'theme': 'white', 'lang': 'en'}
See reCAPTCHA documentation for the available options:
http://code.google.com/apis/recaptcha/docs/customization.html
Adapted in part from http://djangosnippets.org/snippets/1653/
and http://code.google.com/p/recaptcha-django/
An example project that uses this widget is the EmoryFindingAids
feedback form. The form can be viewed on the web at
http://findingaids.library.emory.edu/content/feedback/ . The relevant code
can be found in :mod:`findingaids.content.forms`
----
'''

# NOTE to Developers: recaptcha field & widget are separate from other
# form fields because it requires the installation of python-recaptcha

import json
from recaptcha.client import captcha
from django.conf import settings
from django.forms import CharField, ValidationError
from django.forms.widgets import Widget
from django.utils.safestring import mark_safe


class ReCaptchaWidget(Widget):
    '''reCAPTCHA widget.  Rendering this widget on a form will generate and
    display a reCAPTCHA challenge.  reCAPTCHA customization options (such as theme,
    lang) can be passed as widget attributes.
    :param use_ssl: Default=True  passed to :meth:`captcha.displayhtml`
    '''
    def __init__(self, use_ssl=True, *args, **kwargs):
        self.use_ssl = use_ssl
        super(ReCaptchaWidget, self).__init__(*args, **kwargs)

    is_hidden = True
    # hidden input field names that will be added to the form via captcha.displayhtml
    recaptcha_challenge_name = 'recaptcha_challenge_field'
    recaptcha_response_name = 'recaptcha_response_field'
    remote_ip_name = 'remote_ip'

    options = ['theme', 'lang', 'custom_translations', 'custom_theme_widget', 'tabindex']

    def render(self, name, value, attrs=None):
        'Render the widget in HTML form - display the captcha challenge'
        final_attrs = self.build_attrs(attrs)
        # get global options from settings, if any
        captcha_opts = getattr(settings, 'RECAPTCHA_OPTIONS', {})
        # update those with any locally-specified options
        captcha_opts.update(dict((k, v) for k, v in final_attrs.items() if k in self.options))        
        # if there are any Recaptcha options to specify, include javascript when rendering
        if captcha_opts:
            html_opts = '''<script type="text/javascript">
                                var RecaptchaOptions = %s;
                           </script>''' % json.dumps(captcha_opts)
        else:
            html_opts = ''
        return mark_safe(u'%s %s' % (html_opts, captcha.displayhtml(settings.RECAPTCHA_PUBLIC_KEY, self.use_ssl)))

    def value_from_datadict(self, data, files, name):
        'Generate a dictionary of the values needed to check the captcha response'
        return {'challenge': data.get(self.recaptcha_challenge_name, None),
            'response': data.get(self.recaptcha_response_name, None),
            'remote_ip': data.get(self.remote_ip_name, None)}


class ReCaptchaField(CharField):
    '''reCAPTCHA form field that uses a :class:`~eulcore.django.forms.captchafield.ReCaptchaWidget`
    for presentation and submits the captcha challenge & resonse for validation.
    '''
    widget = ReCaptchaWidget
    required = True
    default_error_messages = {
        'captcha_invalid': u'CAPTCHA response was incorrect',
        'captcha_error': u'Error validating CAPTCHA',
    }

    def clean(self, values):
        challenge = values.get('challenge', None)
        response = values.get('response', None)
        remote_ip = values.get('remote_ip', None)
        captcha_response = captcha.submit(challenge, response,
            settings.RECAPTCHA_PRIVATE_KEY, remote_ip)
        if not captcha_response.is_valid:
            # incorrect solution (only error a user should normally see)
            if captcha_response.error_code == 'incorrect-captcha-sol':
                raise ValidationError(self.error_messages['captcha_invalid'])
            else:
                msg = self.error_messages['captcha_error']
                # in Debug mode, include actual error message, since it may help
                # track down a configuration issue or similar problem
                if settings.DEBUG:
                    msg = '%s - %s' % (msg, captcha_response.error_code.strip("'"))
                raise ValidationError(msg)
        return challenge
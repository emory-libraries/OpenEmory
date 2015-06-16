from django.conf import settings
from django.shortcuts import render
from downtime.middleware import DowntimeMiddleware

class DownpageMiddleware(DowntimeMiddleware):

    def process_request(self, request):
        def get_client_ip(request):
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            return ip

        downtime_request = super(DownpageMiddleware,self).process_request(request)
        
        if downtime_request and \
            settings.DOWNTIME_ALLOWED_IPS and \
            get_client_ip(request) in settings.DOWNTIME_ALLOWED_IPS:
            return None
        else:
            return downtime_request

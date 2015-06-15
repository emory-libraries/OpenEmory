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

        if settings.DOWNTIME_ALLOWED_IPS and \
            get_client_ip(request) not in settings.DOWNTIME_ALLOWED_IPS:
            return render(request, "downtime/downtime.html", status=503)
        else:
            return super(DownpageMiddleware,self).process_request(request)

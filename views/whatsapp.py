import logging

from django.shortcuts import redirect
from django.views import View
from django.contrib.sites.models import Site
from django.conf import settings as djangosettings

logger = logging.getLogger(__name__)


class WhatsappView(View):
    def get(self, request):
        port = getattr(djangosettings, 'WHATSAPP', {}).get('PORT')
        domain = Site.objects.get_current().domain
        return redirect(f"http://{domain}:{port}/docs/")

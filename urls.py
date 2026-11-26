import logging
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound
from django.urls import path, include, re_path

from whatsapp import views

logger = logging.getLogger(__name__)
cwd = Path(__file__).resolve().parent.parent


app_name = 'whatsapp'
urlpatterns = [
    re_path(r'^dashboard/$', views.WhatsappView.as_view(), name='dashboard'),
    re_path(r'^webhook/?$', views.WebhookView.as_view(), name='webhook'),

    path('api/', include('whatsapp.apis.urls'), name='whatsapp'),
]
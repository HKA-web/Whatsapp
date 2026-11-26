from django.urls import path, include
from rest_framework import routers

from whatsapp.apis import views #change this

router = routers.DefaultRouter()
router.register('inbox', views.InboxViewSet, basename='inbox')
router.register('session', views.SessionViewSet, basename='session')
router.register('outbox', views.OutboxViewSet, basename='outbox')
router.register('template', views.TemplateViewSet, basename='template')
router.register('sent', views.SentViewSet, basename='sent')
router.register('command', views.CommandViewSet, basename='command')

app_name = 'api'
urlpatterns = [
    path('', include(router.urls), name='api'),
]

from whatsapp.apis.views.inbox import InboxViewSet
from whatsapp.apis.views.outbox import OutboxViewSet
from whatsapp.apis.views.session import SessionViewSet
from whatsapp.apis.views.template import TemplateViewSet
from whatsapp.apis.views.sent import SentViewSet
from whatsapp.apis.views.command import CommandViewSet

__all__ = [
    InboxViewSet,
    OutboxViewSet,
    SessionViewSet,
    TemplateViewSet,
    SentViewSet,
    CommandViewSet,
]

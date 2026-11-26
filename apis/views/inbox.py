import logging
from core.apis.viewsets import DevExtremeModelViewSet
from whatsapp.models import Inbox
from whatsapp.apis.serializers.inbox import InboxSerializer

logger = logging.getLogger(__name__)


class InboxViewSet(DevExtremeModelViewSet, ):
    permission_classes = []
    serializer_class = InboxSerializer
    queryset = Inbox.objects.using('WHATSAPP').all()
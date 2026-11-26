import logging
from core.apis.viewsets import DevExtremeModelViewSet
from whatsapp.models import Outbox
from whatsapp.apis.serializers.outbox import OutboxSerializer

logger = logging.getLogger(__name__)


class OutboxViewSet(DevExtremeModelViewSet, ):
    permission_classes = []
    serializer_class = OutboxSerializer
    queryset = Outbox.objects.using('WHATSAPP').all()

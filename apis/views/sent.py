import logging
from core.apis.viewsets import DevExtremeModelViewSet
from whatsapp.models import Sent
from whatsapp.apis.serializers.sent import SentSerializer

logger = logging.getLogger(__name__)


class SentViewSet(DevExtremeModelViewSet, ):
    permission_classes = []
    serializer_class = SentSerializer
    queryset = Sent.objects.using('WHATSAPP').all()

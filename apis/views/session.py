import logging
from core.apis.viewsets import DevExtremeModelViewSet
from whatsapp.models import Session
from whatsapp.apis.serializers.session import SessionSerializer

logger = logging.getLogger(__name__)


class SessionViewSet(DevExtremeModelViewSet, ):
    permission_classes = []
    serializer_class = SessionSerializer
    queryset = Session.objects.using('WHATSAPP').all()
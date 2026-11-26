import logging
from core.apis.viewsets import DevExtremeModelViewSet
from whatsapp.models import Command
from whatsapp.apis.serializers.command import CommandSerializer

logger = logging.getLogger(__name__)


class CommandViewSet(DevExtremeModelViewSet):
    permission_classes = []
    serializer_class = CommandSerializer
    queryset = Command.objects.using('WHATSAPP').all()

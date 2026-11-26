import logging
from core.apis.viewsets import DevExtremeModelViewSet
from whatsapp.models import Template
from whatsapp.apis.serializers.template import TemplateSerializer

logger = logging.getLogger(__name__)


class TemplateViewSet(DevExtremeModelViewSet, ):
    permission_classes = []
    serializer_class = TemplateSerializer
    queryset = Template.objects.using('WHATSAPP').all()
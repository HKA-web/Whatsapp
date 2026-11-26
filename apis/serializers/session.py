import logging
from core.apis.datetime import DateTimeModelSerializer
from library.restframeworkflexfields import FlexFieldsModelSerializer

from whatsapp.models import Session

logger = logging.getLogger(__name__)

class SessionSerializer(FlexFieldsModelSerializer, DateTimeModelSerializer, ):
    class Meta:
        model = Session
        fields = [
            'base64pk',
            'session_id',
            'session_name',
            'premised',
            'server',
            'data',
            'created',
            'modified',
            'read_only',
            'enable',
            'properties',
            'description',
        ]
        extra_kwargs = {
            'base64pk': {'required': False, },
            'session_id': {'required': False, },
            'server': {'required': False, },
        }

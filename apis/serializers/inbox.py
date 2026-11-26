import logging
from core.apis.datetime import DateTimeModelSerializer
from library.restframeworkflexfields import FlexFieldsModelSerializer

from whatsapp.models import Inbox

logger = logging.getLogger(__name__)

class InboxSerializer(FlexFieldsModelSerializer, DateTimeModelSerializer, ):
    class Meta:
        model = Inbox
        fields = [
            'base64pk',
            'inbox_id',
            'message',
            'message_type',
            'inbox_by',
            'inbox_date',
            'is_processed',
            'data',
            'session_id',
            'created',
            'modified',
            'read_only',
            'enable',
            'properties',
            'description',
        ]
        extra_kwargs = {
            'base64pk': {'required': False, },
            'inbox_id': {'required': False, },
            'data': {'required': False, },
        }
        expandable_fields = {
            'session': (
                'whatsapp.apis.serializers.SessionSerializer', {'many': False, },
            )
        }
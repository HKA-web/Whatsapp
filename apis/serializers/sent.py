import logging
from core.apis.datetime import DateTimeModelSerializer
from library.restframeworkflexfields import FlexFieldsModelSerializer
from whatsapp.models import Sent

logger = logging.getLogger(__name__)


class SentSerializer(FlexFieldsModelSerializer, DateTimeModelSerializer, ):
    class Meta:
        model = Sent
        fields = [
            'base64pk',
            'sent_id',
            'message',
            'message_type',
            'sent_for',
            'sent_date',
            'prepare_date',
            'retry',
            'scheduled',
            'scheduled_date',
            'is_interactive',
            'is_answered',
            'answered_date',
            'data',
            'session_id',
            'template_id',
            'created',
            'modified',
            'read_only',
            'enable',
            'properties',
            'description',
            'status',
        ]
        extra_kwargs = {
            'base64pk': {'required': False, },
            'sent_id': {'required': False, },
            'sent_date': {'required': False, },
            'prepare_date': {'required': False, },
            'retry': {'required': False, },
            'scheduled': {'required': False, },
            'scheduled_date': {'required': False, },
            'is_interactive': {'required': False, },
            'is_answered': {'required': False, },
            'answered_date': {'required': False, },
            'data': {'required': False, },
            'created': {'required': False, },
            'modified': {'required': False, },
            'read_only': {'required': False, },
            'enable': {'required': False, },
            'properties': {'required': False, },
            'description': {'required': False, },
        }
        expandable_fields = {
            'session': (
                'whatsapp.apis.serializers.SessionSerializer', {'many': False, },
            ),
            'template': (
                'whatsapp.apis.serializers.TemplateSerializer', {'many': False, },
            ),
        }

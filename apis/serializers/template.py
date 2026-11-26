import logging
from rest_framework import serializers
from core.apis.datetime import DateTimeModelSerializer
from library.restframeworkflexfields import FlexFieldsModelSerializer

from whatsapp.models import Template

logger = logging.getLogger(__name__)

class TemplateSerializer(FlexFieldsModelSerializer, DateTimeModelSerializer, ):
    content_template = serializers.SerializerMethodField(method_name='get_content_template', )

    class Meta:
        model = Template
        fields = [
            'base64pk',
            'template_id',
            'template_name',
            'template',
            'content_template',
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
            'template_id': {'required': False, },
            'content_template': {'required': False, 'read_only': True, },
        }
        expandable_fields = {
            'session': (
                'whatsapp.apis.serializers.SessionSerializer', {'many': False, },
            ),
        }

    def get_content_template(self, instance):
        return instance.template

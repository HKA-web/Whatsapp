import logging
from rest_framework import serializers
from core.apis.datetime import DateTimeModelSerializer
from library.restframeworkflexfields import FlexFieldsModelSerializer

from whatsapp.models import Outbox

logger = logging.getLogger(__name__)

class OutboxSerializer(FlexFieldsModelSerializer, DateTimeModelSerializer, ):
    simulateTyping = serializers.BooleanField(required=False, default=None, allow_null=True, write_only=True)
    typingDelay = serializers.IntegerField(required=False, default=None, allow_null=True, write_only=True)

    class Meta:
        model = Outbox
        fields = [
            'base64pk',
            'outbox_id',
            'template_id',
            'message',
            'message_type',
            'outbox_for',
            'prepare_date',
            'retry',
            'scheduled',
            'scheduled_date',
            'is_interactive',
            'is_answered',
            'answered_date',
            'data',
            'session_id',
            'created',
            'modified',
            'read_only',
            'enable',
            'properties',
            'description',
            'simulateTyping',
            'typingDelay',
        ]
        extra_kwargs = {
            'base64pk': {'required': False, },
            'outbox_id': {'required': False, },
            'template_id': {'required': False, 'allow_null': True, 'allow_blank': True, },
            'message': {'required': False, 'allow_null': True, 'allow_blank': True, },
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

    def create(self, validated_data):
        using_db = validated_data.pop('using', 'WHATSAPP')
        simulate_typing = validated_data.pop('simulateTyping', None)
        typing_delay = validated_data.pop('typingDelay', None)

        if simulate_typing is not None or typing_delay is not None:
            properties = validated_data.setdefault('properties', {})
            if not isinstance(properties, dict):
                properties = {}
                validated_data['properties'] = properties
            if simulate_typing is not None:
                properties['simulateTyping'] = simulate_typing
            if typing_delay is not None:
                properties['typingDelay'] = typing_delay

        return Outbox.objects.using(using_db).create(**validated_data)

    def update(self, instance, validated_data):
        using_db = validated_data.pop('using', 'WHATSAPP')
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(using=using_db)
        return instance


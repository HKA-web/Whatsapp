import logging
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from core.apis.datetime import DateTimeModelSerializer
from library.restframeworkflexfields import FlexFieldsModelSerializer
from whatsapp.models import Command

logger = logging.getLogger(__name__)


class CommandSerializer(FlexFieldsModelSerializer, DateTimeModelSerializer):
    command_id = serializers.CharField(
        max_length=100,
        required=False,
        validators=[UniqueValidator(queryset=Command.objects.using('WHATSAPP').all())],
    )
    mirror = serializers.PrimaryKeyRelatedField(
        queryset=Command.objects.using('WHATSAPP').all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Command
        fields = [
            'base64pk',
            'command_id',
            'command_name',
            'mirror',
            'command',
            'command_type',
            'process',
            'required_parameter',
            'check_parameter',
            'required_permission',
            'check_permission',
            'is_finish',
            'session_id',
            'created',
            'modified',
            'read_only',
            'enable',
            'properties',
            'description',
        ]
        extra_kwargs = {
            'base64pk': {'required': False},
            'command_id': {'required': False},
            'command_name': {'required': True},
            'command': {'required': True},
            'command_type': {'required': True},
            'process': {'required': False},
            'required_parameter': {'required': False},
            'required_permission': {'required': False},
            'properties': {'required': False},
            'created': {'required': False},
            'modified': {'required': False},
            'read_only': {'required': False},
            'enable': {'required': False},
            'description': {'required': False},
            'check_parameter': {'required': False},
            'check_permission': {'required': False},
            'is_finish': {'required': False},
            'session_id': {'required': False},
            'status': {'required': False},
        }
        expandable_fields = {
            'session': (
                'whatsapp.apis.serializers.SessionSerializer', {'many': False},
            ),
            'mirror': (
                'whatsapp.apis.serializers.CommandSerializer', {'many': False},
            ),
        }

    def create(self, validated_data):
        using_db = validated_data.pop('using', 'WHATSAPP')
        if not validated_data.get('command_id'):
            from core.utils import ShortUUID
            validated_data['command_id'] = f"CMD_{ShortUUID().random(length=10)}"
        return Command.objects.using(using_db).create(**validated_data)

    def update(self, instance, validated_data):
        using_db = validated_data.pop('using', 'WHATSAPP')
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(using=using_db)
        return instance

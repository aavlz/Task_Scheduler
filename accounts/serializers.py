import base64

from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import PendingRegistration, UserProfile


MAX_AVATAR_UPLOAD_BYTES = 2 * 1024 * 1024


def validate_strong_password(value):
    try:
        validate_password(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))
    checks = [
        (len(value) >= 8, 'Password must be at least 8 characters.'),
        (any(char.isupper() for char in value), 'Password must include an uppercase letter.'),
        (any(char.islower() for char in value), 'Password must include a lowercase letter.'),
        (any(char.isdigit() for char in value), 'Password must include a number.'),
        (any(not char.isalnum() for char in value), 'Password must include a special character.'),
    ]
    errors = [message for passed, message in checks if not passed]
    if errors:
        raise serializers.ValidationError(errors)
    return value


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email is already in use.")
        return value

    def validate_password(self, value):
        return validate_strong_password(value)
    
    def create(self, validated_data):
        validated_data['password_hash'] = make_password(validated_data.pop('password'))
        return PendingRegistration.objects.create(**validated_data)

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower().strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        return validate_strong_password(value)

class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    avatar_image = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'username',
            'full_name',
            'first_name',
            'last_name',
            'email',
            'avatar_bg_color',
            'avatar_image',
            'language',
            'region',
            'is_verified',
            'morning_motivation_enabled',
            'evening_summary_enabled',
            'device_notifications_enabled',
        ]
        read_only_fields = ['username', 'full_name', 'first_name', 'last_name', 'email', 'is_verified']
    
    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_avatar_image(self, obj):
        if obj.avatar_data_url:
            return obj.avatar_data_url
        if obj.avatar_image:
            try:
                request = self.context.get('request')
                url = obj.avatar_image.url
                return request.build_absolute_uri(url) if request else url
            except ValueError:
                return ''
        return ''

    def to_internal_value(self, data):
        avatar_input = data.get('avatar_image') if hasattr(data, 'get') else None
        mutable_data = data.copy() if hasattr(data, 'copy') else data
        if hasattr(mutable_data, 'pop'):
            mutable_data.pop('avatar_image', None)
        if hasattr(mutable_data, 'get') and mutable_data.get('avatar_bg_color') == '':
            mutable_data['avatar_bg_color'] = '#338A85'

        internal = super().to_internal_value(mutable_data)
        if avatar_input is not None:
            internal['avatar_image_input'] = avatar_input
        if internal.get('avatar_bg_color') == '':
            internal['avatar_bg_color'] = '#338A85'
        return internal

    def validate_avatar_bg_color(self, value):
        if not value:
            return '#338A85'
        if not isinstance(value, str) or not value.startswith('#') or len(value) != 7:
            raise serializers.ValidationError('Enter a valid hex color such as #338A85.')
        return value

    def _avatar_to_data_url(self, avatar_file):
        if avatar_file == '':
            return ''
        if not hasattr(avatar_file, 'read'):
            return None
        if getattr(avatar_file, 'size', 0) > MAX_AVATAR_UPLOAD_BYTES:
            raise serializers.ValidationError({'avatar_image': 'Avatar image must be 2 MB or smaller.'})

        content_type = getattr(avatar_file, 'content_type', '') or 'image/png'
        if not content_type.startswith('image/'):
            raise serializers.ValidationError({'avatar_image': 'Upload a valid image file.'})

        encoded = base64.b64encode(avatar_file.read()).decode('ascii')
        return f'data:{content_type};base64,{encoded}'

    def update(self, instance, validated_data):
        avatar_input = validated_data.pop('avatar_image_input', None)
        if avatar_input is not None:
            data_url = self._avatar_to_data_url(avatar_input)
            if data_url is not None:
                instance.avatar_data_url = data_url
                if data_url == '':
                    instance.avatar_image = None
        return super().update(instance, validated_data)
    
class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        return validate_strong_password(value)


class VerifyAccountSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    code = serializers.CharField(max_length=6)

    def validate(self, attrs):
        if not attrs.get('email'):
            raise serializers.ValidationError('Provide an email.')
        code = attrs.get('code', '')
        if not code.isdigit() or len(code) != 6:
            raise serializers.ValidationError({'code': 'Enter a complete 6-digit verification code.'})
        return attrs


class ChangeEmailSerializer(serializers.Serializer):
    new_email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_new_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email is already in use.')
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.check_password(attrs.get('password', '')):
            raise serializers.ValidationError({'password': 'Password is incorrect.'})
        return attrs


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.check_password(attrs.get('password', '')):
            raise serializers.ValidationError({'password': 'Password is incorrect.'})
        return attrs
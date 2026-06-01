from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import PendingRegistration, UserProfile


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

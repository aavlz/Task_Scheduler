from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password
from urllib.parse import urlencode
import random
import secrets
import string

from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
    VerifyAccountSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    ChangeEmailSerializer,
    DeleteAccountSerializer,
)
from .models import PendingRegistration, UserProfile


VERIFICATION_EXPIRY_MINUTES = 5


def generate_username_id():
    alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits
    while True:
        username = ''.join(secrets.choice(alphabet) for _ in range(8))
        if not User.objects.filter(username=username).exists():
            return username

# Create your views here.

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Generate a 6-digit verification code and store on profile
        code = f"{random.randint(0, 999999):06d}"
        email = serializer.validated_data['email']
        now = timezone.now()
        pending, _ = PendingRegistration.objects.update_or_create(
            email=email,
            defaults={
                'password_hash': make_password(serializer.validated_data['password']),
                'verification_code': code,
                'verification_sent_at': now,
                'expires_at': now + timezone.timedelta(minutes=VERIFICATION_EXPIRY_MINUTES),
            },
        )

        # Send verification email (SendGrid SMTP is expected to be configured in settings)
        subject = 'V.A.S.T. Account Verification Code'
        message = (
            f'Your V.A.S.T. verification code is: {code}\n\n'
            f'This code expires in {VERIFICATION_EXPIRY_MINUTES} minutes. '
            'If you did not request this, ignore this email.'
        )
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        try:
            send_mail(subject, message, from_email, [email], fail_silently=False)
        except Exception:
            if not settings.DEBUG:
                return Response({'detail': 'Account created but failed to send verification email. Contact support.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        payload = {
            'email': pending.email,
            'expires_in_seconds': VERIFICATION_EXPIRY_MINUTES * 60,
            'message': 'Verification code sent. Please verify your account.',
        }
        if settings.DEBUG:
            payload['dev_verification_code'] = code
        return Response(payload, status=status.HTTP_201_CREATED)

class VerifyAccountView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email'].lower().strip()
        code = serializer.validated_data['code']

        try:
            pending = PendingRegistration.objects.get(email__iexact=email)
        except PendingRegistration.DoesNotExist:
            pending = None

        if pending is None:
            try:
                user = User.objects.get(email__iexact=email)
                profile = UserProfile.objects.get(user=user)
            except (User.DoesNotExist, UserProfile.DoesNotExist):
                return Response({'detail': 'No pending verification found for this email.'}, status=status.HTTP_404_NOT_FOUND)

            if profile.is_verified:
                return Response({'detail': 'Account is already verified.'}, status=status.HTTP_400_BAD_REQUEST)
            if not profile.verification_sent_at or profile.verification_sent_at + timezone.timedelta(minutes=VERIFICATION_EXPIRY_MINUTES) <= timezone.now():
                return Response({'detail': 'Verification code expired. Please request a new code.'}, status=status.HTTP_400_BAD_REQUEST)
            if profile.verification_code != code:
                return Response({'detail': 'Invalid verification code.'}, status=status.HTTP_400_BAD_REQUEST)

            profile.is_verified = True
            profile.verification_code = None
            profile.verification_sent_at = timezone.now()
            profile.save()
            login(request, user)
            return Response({
                'detail': 'Account verified and activated.',
                'username': user.username,
                'email': user.email,
                'is_verified': profile.is_verified,
            })

        if pending.expires_at <= timezone.now():
            pending.delete()
            return Response({'detail': 'Verification code expired. Please register again.'}, status=status.HTTP_400_BAD_REQUEST)

        if pending.verification_code != code:
            return Response({'detail': 'Invalid verification code.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email__iexact=email).exists():
            pending.delete()
            return Response({'detail': 'Email is already registered.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create(
            username=generate_username_id(),
            email=pending.email,
            password=pending.password_hash,
            is_active=True,
        )
        profile = UserProfile.objects.create(
            user=user,
            is_verified=True,
            verification_code=None,
            verification_sent_at=timezone.now(),
        )
        pending.delete()

        login(request, user)

        return Response({
            'detail': 'Account verified and activated.',
            'username': user.username,
            'email': user.email,
            'is_verified': profile.is_verified,
        })


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        login_or_email = serializer.validated_data['username']
        password = serializer.validated_data['password']

        user = authenticate(username=login_or_email, password=password)
        if user is None:
            try:
                user_obj = User.objects.get(email__iexact=login_or_email)
            except User.DoesNotExist:
                user_obj = None

            if user_obj is not None:
                user = authenticate(username=user_obj.username, password=password)

        if user is None:
            return Response(
                {'error': 'Invalid username or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        profile, _ = UserProfile.objects.get_or_create(user=user)
        if not profile.is_verified:
            return Response(
                {
                    'error': 'Account is not verified.',
                    'requires_verification': True,
                    'username': user.username,
                    'email': user.email,
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        login(request, user)

        return Response({
            'username': user.username,
            'name': user.get_full_name() or user.username,
            'email': user.email,
            'is_verified': profile.is_verified,
        })


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        generic_response = {'detail': 'If an account exists for this email, a password reset link has been sent.'}

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(generic_response)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = request.build_absolute_uri('/') + '?' + urlencode({
            'reset_uid': uid,
            'reset_token': token,
        })
        subject = 'Reset your V.A.S.T. password'
        message = (
            'We received a request to reset your V.A.S.T. password.\n\n'
            f'Open this link to set a new password:\n{reset_url}\n\n'
            'This link expires soon and can only be used for this account.\n\n'
            'If you did not request a new password, you can ignore this email. '
            'Your current password will remain unchanged.'
        )
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        except Exception:
            if not settings.DEBUG:
                return Response({'detail': 'Unable to send password reset email. Contact support.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        payload = dict(generic_response)
        if settings.DEBUG:
            payload['dev_reset_url'] = reset_url
        return Response(payload)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            uid = force_str(urlsafe_base64_decode(serializer.validated_data['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'detail': 'Invalid password reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, serializer.validated_data['token']):
            return Response({'detail': 'Invalid or expired password reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'detail': 'Password has been reset successfully.'})

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({'message': 'Logged out successfully'})
    
class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        serializer = UserProfileSerializer(profile, context={'request': request})
        return Response(serializer.data)
    
    def patch(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        new_username = None
        new_email = None

        # Validate user fields before saving anything.
        if 'username' in request.data:
            new_username = request.data['username'].strip()
            if len(new_username) < 3:
                return Response({'username': 'Username must be at least 3 characters.'}, status=status.HTTP_400_BAD_REQUEST)
            if User.objects.filter(username__iexact=new_username).exclude(pk=request.user.pk).exists():
                return Response({'username': 'This username is already in use.'}, status=status.HTTP_400_BAD_REQUEST)
        if 'email' in request.data:
            new_email = request.data['email'].lower().strip()
            # Check if email is already used by another user
            if User.objects.filter(email=new_email).exclude(pk=request.user.pk).exists():
                return Response(
                    {'email': 'This email is already in use.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Update profile fields, including file uploads
        serializer = UserProfileSerializer(profile, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            if new_username is not None:
                request.user.username = new_username
            if new_email is not None:
                request.user.email = new_email
            if new_username is not None or new_email is not None:
                request.user.save()
                request.user.refresh_from_db()
            serializer.save()

        return Response(serializer.data)

    def delete(self, request):
        user = request.user
        logout(request)
        user.delete()
        return Response({'message': 'Account deleted successfully.'}, status=status.HTTP_200_OK)
    
class ChangeEmailView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangeEmailSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        new_email = serializer.validated_data['new_email']
        user = request.user

        # Confirm password already validated in serializer
        user.email = new_email
        # mark as unverified until user re-verifies
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.is_verified = False
        code = f"{random.randint(0, 999999):06d}"
        profile.verification_code = code
        profile.verification_sent_at = timezone.now()
        profile.save()
        # Keep user active but require re-verification of email
        user.save()

        # send verification to new email
        subject = 'V.A.S.T. Email Change Verification Code'
        message = f'Your email change verification code is: {code}'
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        try:
            send_mail(subject, message, from_email, [new_email], fail_silently=False)
        except Exception:
            if not settings.DEBUG:
                return Response({'detail': 'Email updated but failed to send verification email.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        payload = {'detail': 'Email updated. Verification required for new email.'}
        if settings.DEBUG:
            payload['dev_verification_code'] = code
        return Response(payload)


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeleteAccountSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        user = request.user
        logout(request)
        user.delete()
        return Response({'detail': 'Account deleted successfully.'}, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()

        # Re-login so session isn't invalidated
        login(request, request.user)

        return Response({'message': 'Password changed successfully'})

class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'status': 'ok'}, status=status.HTTP_200_OK)


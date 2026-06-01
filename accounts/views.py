from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User

from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
)
from .models import UserProfile

# Create your views here.

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)

        return Response({
            'username': user.username,
            'name': user.get_full_name() or user.username,
            'email': user.email,
        }, status=status.HTTP_201_CREATED)

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
        
        login(request, user)

        return Response({
            'username': user.username,
            'name': user.get_full_name() or user.username,
            'email': user.email,
        })

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
        serializer = UserProfileSerializer(profile)
        return Response(serializer.data)
    
    def patch(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        # Update user fields if provided
        if 'first_name' in request.data:
            request.user.first_name = request.data['first_name']
        if 'last_name' in request.data:
            request.user.last_name = request.data['last_name']
        if 'email' in request.data:
            new_email = request.data['email'].lower().strip()
            # Check if email is already used by another user
            if User.objects.filter(email=new_email).exclude(pk=request.user.pk).exists():
                return Response(
                    {'email': 'This email is already in use.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            request.user.email = new_email
        request.user.save()

        # Refresh user from database to ensure changes are reflected in serializer
        request.user.refresh_from_db()

        # Update profile fields, including file uploads
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    def delete(self, request):
        user = request.user
        logout(request)
        user.delete()
        return Response({'message': 'Account deleted successfully.'}, status=status.HTTP_200_OK)
    
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
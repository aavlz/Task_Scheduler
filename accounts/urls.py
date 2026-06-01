from django.urls import path
from .views import (
    RegisterView,
    VerifyAccountView,
    LoginView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    LogoutView,
    ProfileView,
    ChangePasswordView,
    ChangeEmailView,
    DeleteAccountView,
    HealthCheckView,
)

urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='health'),
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-account/', VerifyAccountView.as_view(), name='verify_account'),
    path('login/', LoginView.as_view(), name='login'),
    path('password-reset/request/', PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('change-email/', ChangeEmailView.as_view(), name='change_email'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete_account'),
]

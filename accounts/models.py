from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class PendingRegistration(models.Model):
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=128)
    verification_code = models.CharField(max_length=6)
    verification_sent_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Pending registration: {self.email}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar_bg_color = models.CharField(max_length=7, default='#338A85')
    avatar_image = models.ImageField(upload_to='avatars/', blank=True, null=True)
    avatar_data_url = models.TextField(blank=True, default='')
    language = models.CharField(max_length=20, default='English (US)')
    region = models.CharField(max_length=30, default='Philippines (GMT+8)')

    # Email verification fields
    is_verified = models.BooleanField(default=False)
    verification_code = models.CharField(max_length=6, blank=True, null=True)
    verification_sent_at = models.DateTimeField(blank=True, null=True)

    # Notification preferences
    morning_motivation_enabled = models.BooleanField(default=True)
    evening_summary_enabled = models.BooleanField(default=True)
    device_notifications_enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile: {self.user.username}"
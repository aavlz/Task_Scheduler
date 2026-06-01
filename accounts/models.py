from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar_bg_color = models.CharField(max_length=7, default='#338A85')
    avatar_image = models.ImageField(upload_to='avatars/', blank=True, null=True)
    language = models.CharField(max_length=50, default='English(US)')
    region = models.CharField(max_length=50, default='Philippines (English)')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile: {self.user.username}"
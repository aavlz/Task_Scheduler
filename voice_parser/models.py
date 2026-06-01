from django.conf import settings
from django.db import models


class VoiceCommand(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='voice_commands')
    transcript = models.TextField()
    intent = models.CharField(max_length=64)
    confidence = models.FloatField(default=0)
    action = models.CharField(max_length=64, blank=True)
    response_message = models.TextField(blank=True)
    success = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['intent']),
        ]


class VoiceAnalytics(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='voice_analytics')
    total_commands = models.PositiveIntegerField(default=0)
    successful_commands = models.PositiveIntegerField(default=0)
    last_command_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

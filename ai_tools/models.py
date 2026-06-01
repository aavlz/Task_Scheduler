from django.conf import settings
from django.db import models


class AIInsight(models.Model):
    INSIGHT_TYPES = [
        ('summary', 'Summary'),
        ('recommendation', 'Recommendation'),
        ('voice_intent', 'Voice Intent'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_insights')
    insight_type = models.CharField(max_length=32, choices=INSIGHT_TYPES)
    prompt = models.TextField(blank=True)
    response = models.JSONField(default=dict)
    used_external_ai = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

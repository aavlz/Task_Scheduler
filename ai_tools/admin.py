from django.contrib import admin

from .models import AIInsight


@admin.register(AIInsight)
class AIInsightAdmin(admin.ModelAdmin):
    list_display = ('user', 'insight_type', 'used_external_ai', 'created_at')
    list_filter = ('insight_type', 'used_external_ai')
    search_fields = ('user__username', 'prompt')

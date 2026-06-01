from django.contrib import admin

from .models import VoiceAnalytics, VoiceCommand


@admin.register(VoiceCommand)
class VoiceCommandAdmin(admin.ModelAdmin):
    list_display = ('user', 'intent', 'confidence', 'success', 'created_at')
    list_filter = ('intent', 'success')
    search_fields = ('user__username', 'transcript', 'response_message')


@admin.register(VoiceAnalytics)
class VoiceAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_commands', 'successful_commands', 'last_command_at')

from django.urls import path

from .views import VoiceCommandView, VoiceAudioUploadView

urlpatterns = [
    path('command/', VoiceCommandView.as_view(), name='voice-command'),
    path('audio/', VoiceAudioUploadView.as_view(), name='voice-audio'),
]

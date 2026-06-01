from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from .services import VoiceCommandService


class VoiceCommandView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        transcript = request.data.get('transcript', '').strip()
        if not transcript:
            return Response({'error': 'No transcript provided.'}, status=400)
        result = VoiceCommandService(request.user, request=request).execute(transcript)
        return Response(result)


class VoiceAudioUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        audio = request.FILES.get('audio')
        if not audio:
            return Response({'error': 'No audio file provided.'}, status=400)

        # Transcribe using configured AI service (e.g., OpenAI Whisper)
        from ai_tools.services import AIService

        transcript = AIService(request.user).transcribe_audio(audio)
        if not transcript:
            return Response({'error': 'Transcription failed or not configured.'}, status=500)

        result = VoiceCommandService(request.user, request=request).execute(transcript)
        return Response(result)

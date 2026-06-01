from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import AIService


class TaskSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(AIService(request.user).summarize_tasks())

    def post(self, request):
        return Response(AIService(request.user).summarize_tasks())


class MorningNotificationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = AIService(request.user).prepare_morning_notification()
        return Response(payload)


class EveningNotificationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = AIService(request.user).prepare_evening_notification()
        return Response(payload)

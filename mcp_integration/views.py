from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MCPToolExecution
from .tools import MCPToolRunner


class ToolListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'tools': MCPToolRunner(request.user).list_tools()})


class ToolExecuteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        result = MCPToolRunner(request.user).execute(slug, request.data)
        MCPToolExecution.objects.create(
            user=request.user,
            tool_slug=slug,
            input_payload=request.data or {},
            output_payload=result,
            success=result.get('success', False),
        )
        status_code = 200 if result.get('success') else 404
        return Response(result, status=status_code)

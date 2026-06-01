from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from tasks.models import Task
from .models import MCPToolExecution


class MCPIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='mcp', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_tool_list_and_execution(self):
        Task.objects.create(
            user=self.user,
            title='Deploy to Railway',
            date=date.today(),
            time=time(11, 0),
            priority='high',
        )

        list_response = self.client.get('/api/tools/')
        self.assertEqual(list_response.status_code, 200)
        self.assertGreaterEqual(len(list_response.data['tools']), 3)
        self.assertNotIn('task-analyzer', [tool['slug'] for tool in list_response.data['tools']])

        execute_response = self.client.post('/api/tools/task-recommender/execute/', {}, format='json')
        self.assertEqual(execute_response.status_code, 200)
        self.assertTrue(execute_response.data['success'])
        self.assertEqual(MCPToolExecution.objects.filter(user=self.user).count(), 1)

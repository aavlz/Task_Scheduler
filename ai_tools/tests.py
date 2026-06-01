from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tasks.models import Task


class AIToolTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ai', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @override_settings(GEMINI_API_KEY='', OPENAI_API_KEY='')
    def test_ai_summary_uses_rule_based_fallback_without_api_key(self):
        Task.objects.create(
            user=self.user,
            title='Prepare report',
            date=date.today(),
            time=time(10, 0),
            priority='high',
        )

        response = self.client.post('/api/ai/summary/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('pending task', response.data['summary'])
        self.assertFalse(response.data['used_external_ai'])

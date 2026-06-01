from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from tasks.models import Task
from .models import VoiceCommand


class VoiceCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='voice', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_voice_command_creates_task_with_fallback_parser(self):
        response = self.client.post('/api/voice/command/', {
            'transcript': 'Add math quiz tomorrow at 3 PM priority high'
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['action'], 'create_task')
        self.assertEqual(Task.objects.get(user=self.user).priority, 'high')
        self.assertEqual(VoiceCommand.objects.filter(user=self.user).count(), 1)

    def test_voice_command_completes_task(self):
        Task.objects.create(
            user=self.user,
            title='Project deadline',
            date=date.today(),
            time=time(9, 0),
        )

        response = self.client.post('/api/voice/command/', {
            'transcript': 'Complete task project deadline'
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(Task.objects.get(user=self.user).status, 'completed')

    def test_voice_command_corrects_known_phrase_when_creating_task(self):
        response = self.client.post('/api/voice/command/', {
            'transcript': 'Add up dev assignment tomorrow at 2 PM category School'
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        task = Task.objects.get(user=self.user)
        self.assertEqual(task.title, 'App dev assignment')
        self.assertEqual(response.data['corrected_transcript'], 'Add App Dev assignment tomorrow at 2 PM category School')

    def test_voice_command_fuzzy_matches_existing_task_title(self):
        Task.objects.create(
            user=self.user,
            title='App Dev prototype',
            date=date.today(),
            time=time(9, 0),
        )

        response = self.client.post('/api/voice/command/', {
            'transcript': 'Complete task up dev prototype'
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(Task.objects.get(user=self.user).status, 'completed')

    def test_voice_command_creates_task_from_filipino_phrase(self):
        response = self.client.post('/api/voice/command/', {
            'transcript': 'Magdagdag ng quiz sa math bukas alas tres ng hapon prayoridad mataas kategorya paaralan'
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        task = Task.objects.get(user=self.user)
        self.assertEqual(task.title, 'Quiz math')
        self.assertEqual(task.time, time(15, 0))
        self.assertEqual(task.priority, 'high')
        self.assertEqual(task.category.name, 'School')

    def test_voice_command_removes_by_time_from_task_title(self):
        response = self.client.post('/api/voice/command/', {
            'transcript': 'Add grocery by 8 a.m.'
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        task = Task.objects.get(user=self.user)
        self.assertEqual(task.title, 'Grocery')
        self.assertEqual(task.time, time(8, 0))

    def test_voice_command_completes_task_from_filipino_phrase(self):
        Task.objects.create(
            user=self.user,
            title='Math quiz',
            date=date.today(),
            time=time(9, 0),
        )

        response = self.client.post('/api/voice/command/', {
            'transcript': 'Tapusin ang math quiz'
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(Task.objects.get(user=self.user).status, 'completed')

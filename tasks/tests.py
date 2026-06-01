from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Task


class TaskAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ezrah', password='pass12345')
        self.other_user = User.objects.create_user(username='other', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_and_filter_tasks(self):
        today = timezone.localdate()
        response = self.client.post('/api/tasks/', {
            'title': 'Project deadline',
            'date': today.isoformat(),
            'time': '14:00',
            'priority': 'high',
            'status': 'pending',
            'category_label': 'School',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Task.objects.filter(user=self.user).count(), 1)

        high_response = self.client.get('/api/tasks/?view=high')
        self.assertEqual(high_response.status_code, 200)
        self.assertEqual(len(high_response.data), 1)
        self.assertEqual(high_response.data[0]['category_name'], 'School')

    def test_users_only_see_their_own_tasks(self):
        Task.objects.create(
            user=self.other_user,
            title='Hidden task',
            date=date.today() + timedelta(days=1),
            time=time(9, 0),
        )

        response = self.client.get('/api/tasks/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

# Create your tests here.

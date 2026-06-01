from django.core import mail
from django.core.mail import EmailMessage
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch
import json

from .email_backends import SendGridAPIEmailBackend
from .models import PendingRegistration, UserProfile


class AccountAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_pending_registration_then_verify_creates_user(self):
        response = self.client.post('/api/accounts/register/', {
            'email': 'student@example.com',
            'password': 'StrongPass1!',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(PendingRegistration.objects.filter(email='student@example.com').count(), 1)
        self.assertFalse(UserProfile.objects.filter(user__email='student@example.com').exists())

        pending = PendingRegistration.objects.get(email='student@example.com')
        verify_response = self.client.post('/api/accounts/verify-account/', {
            'email': 'student@example.com',
            'code': pending.verification_code,
        }, format='json')
        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(len(verify_response.data['username']), 8)

        profile_response = self.client.get('/api/accounts/profile/')
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.data['email'], 'student@example.com')
        self.assertTrue(profile_response.data['is_verified'])

    def test_pending_registration_cannot_login_until_verified(self):
        register_response = self.client.post('/api/accounts/register/', {
            'email': 'student@example.com',
            'password': 'StrongPass1!',
        }, format='json')
        self.assertEqual(register_response.status_code, 201)

        login_response = self.client.post('/api/accounts/login/', {
            'username': 'student@example.com',
            'password': 'StrongPass1!',
        }, format='json')
        self.assertEqual(login_response.status_code, 401)

        pending = PendingRegistration.objects.get(email='student@example.com')
        verify_response = self.client.post('/api/accounts/verify-account/', {
            'email': 'student@example.com',
            'code': pending.verification_code,
        }, format='json')
        self.assertEqual(verify_response.status_code, 200)

        login_response = self.client.post('/api/accounts/login/', {
            'username': 'student@example.com',
            'password': 'StrongPass1!',
        }, format='json')
        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.data['is_verified'])

    def test_notification_preferences_persist_from_profile_patch(self):
        self.client.post('/api/accounts/register/', {
            'email': 'student@example.com',
            'password': 'StrongPass1!',
        }, format='json')
        pending = PendingRegistration.objects.get(email='student@example.com')
        self.client.post('/api/accounts/verify-account/', {
            'email': 'student@example.com',
            'code': pending.verification_code,
        }, format='json')

        response = self.client.patch('/api/accounts/profile/', {
            'morning_motivation_enabled': False,
            'evening_summary_enabled': False,
        }, format='json')

        self.assertEqual(response.status_code, 200)
        profile = UserProfile.objects.get(user__email='student@example.com')
        self.assertFalse(profile.morning_motivation_enabled)
        self.assertFalse(profile.evening_summary_enabled)
        self.assertFalse(response.data['morning_motivation_enabled'])
        self.assertFalse(response.data['evening_summary_enabled'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_email_link_sets_new_password(self):
        register_response = self.client.post('/api/accounts/register/', {
            'email': 'student@example.com',
            'password': 'StrongPass1!',
        }, format='json')
        self.assertEqual(register_response.status_code, 201)
        pending = PendingRegistration.objects.get(email='student@example.com')
        self.client.post('/api/accounts/verify-account/', {
            'email': 'student@example.com',
            'code': pending.verification_code,
        }, format='json')
        self.client.post('/api/accounts/logout/')

        response = self.client.post('/api/accounts/password-reset/request/', {
            'email': 'student@example.com',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn('If you did not request a new password, you can ignore this email.', mail.outbox[-1].body)

        reset_url = next(line for line in mail.outbox[-1].body.splitlines() if 'reset_uid=' in line)
        params = parse_qs(urlparse(reset_url).query)
        response = self.client.post('/api/accounts/password-reset/confirm/', {
            'uid': params['reset_uid'][0],
            'token': params['reset_token'][0],
            'new_password': 'NewStrong1!',
        }, format='json')
        self.assertEqual(response.status_code, 200)

        login_response = self.client.post('/api/accounts/login/', {
            'username': 'student@example.com',
            'password': 'NewStrong1!',
        }, format='json')
        self.assertEqual(login_response.status_code, 200)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_rejects_weak_password(self):
        self.client.post('/api/accounts/register/', {
            'email': 'student@example.com',
            'password': 'StrongPass1!',
        }, format='json')
        pending = PendingRegistration.objects.get(email='student@example.com')
        self.client.post('/api/accounts/verify-account/', {
            'email': 'student@example.com',
            'code': pending.verification_code,
        }, format='json')
        self.client.post('/api/accounts/logout/')
        response = self.client.post('/api/accounts/password-reset/request/', {
            'email': 'student@example.com',
        }, format='json')
        reset_url = next(line for line in mail.outbox[-1].body.splitlines() if 'reset_uid=' in line)
        params = parse_qs(urlparse(reset_url).query)

        response = self.client.post('/api/accounts/password-reset/confirm/', {
            'uid': params['reset_uid'][0],
            'token': params['reset_token'][0],
            'new_password': 'weak',
        }, format='json')
        self.assertEqual(response.status_code, 400)


class SendGridAPIEmailBackendTests(TestCase):
    @override_settings(
        DEFAULT_FROM_EMAIL='VAST <verified@example.com>',
        EMAIL_TIMEOUT=7,
        SENDGRID_API_KEY='SG.test-key',
    )
    @patch('accounts.email_backends.request.urlopen')
    def test_sendgrid_api_backend_posts_mail_payload(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.status = 202

        backend = SendGridAPIEmailBackend()
        sent = backend.send_messages([
            EmailMessage(
                subject='Verify your account',
                body='Your code is 123456',
                from_email='VAST <verified@example.com>',
                to=['student@example.com'],
            )
        ])

        self.assertEqual(sent, 1)
        req = mock_urlopen.call_args.args[0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertEqual(mock_urlopen.call_args.kwargs['timeout'], 7)
        self.assertEqual(req.headers['Authorization'], 'Bearer SG.test-key')
        self.assertEqual(payload['from']['email'], 'verified@example.com')
        self.assertEqual(payload['personalizations'][0]['to'][0]['email'], 'student@example.com')
        self.assertEqual(payload['content'][0]['value'], 'Your code is 123456')
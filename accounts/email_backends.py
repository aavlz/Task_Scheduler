import json
from email.utils import parseaddr
from urllib import error, request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class SendGridAPIEmailBackend(BaseEmailBackend):
    """Send email through SendGrid's HTTPS API instead of SMTP."""

    api_url = 'https://api.sendgrid.com/v3/mail/send'

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = getattr(settings, 'SENDGRID_API_KEY', '')
        if not api_key:
            if self.fail_silently:
                return 0
            raise ValueError('SENDGRID_API_KEY is required for SendGridAPIEmailBackend.')

        sent_count = 0
        timeout = getattr(settings, 'EMAIL_TIMEOUT', 10)
        for email_message in email_messages:
            try:
                self._send(email_message, api_key, timeout)
            except Exception:
                if not self.fail_silently:
                    raise
            else:
                sent_count += 1
        return sent_count

    def _send(self, email_message, api_key, timeout):
        from_name, from_email = parseaddr(email_message.from_email)
        personalizations = [
            {
                'to': [
                    self._email_address(address)
                    for address in email_message.to
                ],
            }
        ]
        if email_message.cc:
            personalizations[0]['cc'] = [
                self._email_address(address)
                for address in email_message.cc
            ]
        if email_message.bcc:
            personalizations[0]['bcc'] = [
                self._email_address(address)
                for address in email_message.bcc
            ]

        payload = {
            'personalizations': personalizations,
            'from': {'email': from_email, **({'name': from_name} if from_name else {})},
            'subject': email_message.subject,
            'content': [{'type': 'text/plain', 'value': email_message.body}],
        }

        data = json.dumps(payload).encode('utf-8')
        req = request.Request(
            self.api_url,
            data=data,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                if response.status >= 400:
                    raise error.HTTPError(
                        self.api_url,
                        response.status,
                        response.reason,
                        response.headers,
                        None,
                    )
        except error.HTTPError:
            raise

    def _email_address(self, address):
        name, email = parseaddr(address)
        return {'email': email, **({'name': name} if name else {})}
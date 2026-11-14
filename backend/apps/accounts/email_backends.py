"""
Email backend that sends through Brevo's HTTP API.

Render's free plan blocks outbound SMTP ports, so Django's SMTP backend can't
deliver mail from there. Brevo's transactional API works over HTTPS instead,
and its free tier only needs a verified sender address (no domain).
"""

import logging

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


def _split_address(address):
    """'SimplyFind <no-reply@x.com>' -> {"name": "SimplyFind", "email": "no-reply@x.com"}."""
    from email.utils import parseaddr

    name, email = parseaddr(address)
    contact = {"email": email}
    if name:
        contact["name"] = name
    return contact


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            payload = {
                "sender": _split_address(message.from_email),
                "to": [_split_address(addr) for addr in message.to],
                "subject": message.subject,
                "textContent": message.body,
            }
            for content, mimetype in getattr(message, "alternatives", []):
                if mimetype == "text/html":
                    payload["htmlContent"] = content
            try:
                response = requests.post(
                    BREVO_SEND_URL,
                    json=payload,
                    headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
                    timeout=15,
                )
                response.raise_for_status()
                sent += 1
            except requests.RequestException:
                logger.exception("Brevo email send failed")
                if not self.fail_silently:
                    raise
        return sent

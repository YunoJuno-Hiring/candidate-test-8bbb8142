"""
Outbound webhook models.

A company registers a WebhookEndpoint; system events are delivered to its URL
as signed POST requests, and each delivery is recorded in a WebhookDelivery.
"""

import secrets

from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.db import models

from accounts.models import Company

WEBHOOK_SECRET_BYTES = 32
UNIQUE_COMPANY_URL_CONSTRAINT = 'unique_webhook_endpoint_company_url'

# System events an endpoint can subscribe to. The 'webhook.test' event is not
# listed: it is sent on demand to one endpoint, whatever its subscriptions.
EVENT_TIMESHEET_SUBMITTED = 'timesheet.submitted'
EVENT_TIMESHEET_APPROVED = 'timesheet.approved'
EVENT_CONTRACT_CREATED = 'contract.created'
EVENT_TYPE_CHOICES = [
    (EVENT_TIMESHEET_SUBMITTED, 'Timesheet submitted'),
    (EVENT_TIMESHEET_APPROVED, 'Timesheet approved'),
    (EVENT_CONTRACT_CREATED, 'Contract created'),
]

# Everything a delivery can carry: the subscribable events plus the test event.
EVENT_WEBHOOK_TEST = 'webhook.test'
DELIVERY_EVENT_TYPE_CHOICES = [*EVENT_TYPE_CHOICES, (EVENT_WEBHOOK_TEST, 'Test event')]


def generate_webhook_secret() -> str:
    """Return a new random secret: 32 bytes as 64 hex characters."""
    return secrets.token_hex(WEBHOOK_SECRET_BYTES)


class WebhookEndpointQuerySet(models.QuerySet):
    def subscribed_to(self, event_type: str) -> 'WebhookEndpointQuerySet':
        """Active endpoints that receive event_type: listed, or subscribed to all."""
        return self.filter(active=True).filter(
            models.Q(event_types=[]) | models.Q(event_types__contains=[event_type])
        )


class WebhookEndpoint(models.Model):
    """A company's URL that receives webhook events.

    The secret is generated once when the endpoint is created. Deliveries sign
    the request body with HMAC-SHA256 using it, so the receiver can check that
    the payload came from us. It is stored in plain text because signing needs
    the original value; it must never be logged.
    """

    url = models.URLField(max_length=2048)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='webhook_endpoints')
    active = models.BooleanField(default=True)
    # Empty means the endpoint receives every event type.
    event_types = ArrayField(
        models.CharField(max_length=100, choices=EVENT_TYPE_CHOICES), default=list, blank=True
    )
    secret = models.CharField(max_length=64, default=generate_webhook_secret, editable=False)
    # Endpoints outlive the admin who created them.
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_webhook_endpoints',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)

    objects = WebhookEndpointQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # Unique per company only: companies may share a receiver URL, since
            # each endpoint signs with its own secret.
            models.UniqueConstraint(fields=['company', 'url'], name=UNIQUE_COMPANY_URL_CONSTRAINT),
        ]

    def __str__(self):
        return f'{self.url} ({self.company.name})'


class WebhookDelivery(models.Model):
    """The delivery log: one row per delivery attempt, never updated.

    A retry adds a new row with the next attempt number, so the full history
    of an event shows in the UI. All attempts of an event share its event_id,
    which is also sent in the payload so the receiver can dedupe.
    """

    event_id = models.UUIDField(editable=False)
    event_type = models.CharField(max_length=100, choices=DELIVERY_EVENT_TYPE_CHOICES)
    destination = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries')
    attempt = models.PositiveSmallIntegerField()
    # Set by the delivery service: true when the receiver accepted the request (2xx).
    successful = models.BooleanField()
    # Optional short explanation from the delivery service, e.g. 'HTTP 500' or 'timeout after 10s'.
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'webhook deliveries'
        ordering = ['-created_at']
        constraints = [
            # Makes a repeated report of the same attempt a no-op instead of a duplicate row.
            models.UniqueConstraint(
                fields=['event_id', 'destination', 'attempt'],
                name='unique_webhook_delivery_event_destination_attempt',
            ),
            models.CheckConstraint(condition=models.Q(attempt__gte=1), name='webhook_delivery_attempt_gte_1'),
        ]

    def __str__(self):
        return f'{self.event_type} {self.event_id} attempt {self.attempt} -> {self.destination.url}'

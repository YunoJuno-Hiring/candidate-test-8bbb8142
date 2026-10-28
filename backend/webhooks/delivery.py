"""
Outbound webhook delivery.

A delivery is one signed POST of an already-serialized body to an endpoint,
recorded as a WebhookDelivery row whatever the outcome. Redirects are not
followed: a 3xx counts as a failure, so a body signed for one URL is never
replayed to another, and POST is never silently turned into GET.
"""

import http.client
import logging
import urllib.error
import urllib.request
import uuid

from django.utils import timezone

from accounts.models import Company

from .models import EVENT_WEBHOOK_TEST, WebhookDelivery, WebhookEndpoint
from .payloads import build_event_body
from .signing import build_signed_headers

logger = logging.getLogger(__name__)

DELIVERY_TIMEOUT_SECONDS = 10
TEST_EVENT_MESSAGE = 'This is a test event. No action is needed.'


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def _post(url: str, headers: dict[str, str], body: bytes) -> tuple[bool, str]:
    """POST body to url and return (successful, reason). Never raises for network errors."""
    request = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with _opener.open(request, timeout=DELIVERY_TIMEOUT_SECONDS) as resp:
            status_code = resp.status
    except urllib.error.HTTPError as exc:
        status_code = exc.code
    except TimeoutError:
        return False, f'timeout after {DELIVERY_TIMEOUT_SECONDS}s'
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            return False, f'timeout after {DELIVERY_TIMEOUT_SECONDS}s'
        return False, 'connection failed'
    except (OSError, http.client.HTTPException):
        return False, 'connection failed'
    return 200 <= status_code < 300, f'HTTP {status_code}'


def deliver(
    endpoint: WebhookEndpoint,
    event_id: uuid.UUID,
    event_type: str,
    body: bytes,
    timestamp: int,
    attempt: int,
) -> WebhookDelivery:
    """Send one signed attempt of an event to endpoint and record it.

    Args:
        endpoint: Destination; its secret signs the request.
        event_id: Id of the event in body, shared by all its attempts.
        event_type: Event type recorded in the delivery log.
        body: The exact bytes to send, as built by build_event_body.
        timestamp: Unix seconds when the event was published.
        attempt: Attempt number, starting at 1.

    Returns:
        The WebhookDelivery row saved for this attempt.
    """
    log_context = {
        'endpoint_id': endpoint.id,
        'event_id': str(event_id),
        'event_type': event_type,
        'attempt': attempt,
    }
    logger.debug('webhook_delivery_started', extra=log_context)

    headers = build_signed_headers(endpoint.secret, event_id, timestamp, body)
    is_successful, reason = _post(endpoint.url, headers, body)
    delivery = WebhookDelivery.objects.create(
        event_id=event_id,
        event_type=event_type,
        destination=endpoint,
        attempt=attempt,
        successful=is_successful,
        reason=reason,
    )

    if is_successful:
        logger.info('webhook_delivered', extra={**log_context, 'reason': reason})
    else:
        logger.warning('webhook_delivery_failed', extra={**log_context, 'reason': reason})
    return delivery


def publish_event(company: Company, event_type: str, data: dict) -> list[WebhookDelivery]:
    """Serialize an event once and deliver it to every subscribed endpoint.

    The body bytes and publish timestamp are fixed here, then each endpoint
    signs with its own secret. First attempt only: retries are left for a
    later queue. Delivery failures are recorded; they do not raise.
    """
    created_at = timezone.now()
    event_id = uuid.uuid4()
    body = build_event_body(event_id, event_type, created_at, data)
    timestamp = int(created_at.timestamp())
    endpoints = WebhookEndpoint.objects.filter(company=company).subscribed_to(event_type)
    return [
        deliver(endpoint, event_id, event_type, body, timestamp, attempt=1) for endpoint in endpoints
    ]


def send_test_event(endpoint: WebhookEndpoint) -> WebhookDelivery:
    """Send a single 'webhook.test' event to endpoint, synchronously, without retries.

    Sent whatever the endpoint's subscriptions or active state, so an admin
    can check a receiver before enabling it.
    """
    created_at = timezone.now()
    event_id = uuid.uuid4()
    body = build_event_body(event_id, EVENT_WEBHOOK_TEST, created_at, {'message': TEST_EVENT_MESSAGE})
    return deliver(endpoint, event_id, EVENT_WEBHOOK_TEST, body, int(created_at.timestamp()), attempt=1)

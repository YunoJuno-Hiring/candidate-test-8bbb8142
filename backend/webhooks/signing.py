"""
HMAC-SHA256 signing of webhook requests.

The signed message is "{timestamp}.{body}", so neither the body nor the
timestamp can be changed without breaking the signature. Each request carries:

    X-Webhook-Id:        event id, for receiver-side dedupe
    X-Webhook-Timestamp: unix seconds when the event was published
    X-Webhook-Signature: sha256=<hex digest>

Requests are signed once at publish time and the queue retries the same bytes,
so the timestamp can be hours old on a late retry. Receivers should dedupe on
X-Webhook-Id rather than reject requests by age.

The HMAC key is the endpoint secret string encoded as UTF-8 (the hex text
itself, not hex-decoded bytes).
"""

import hashlib
import hmac
import uuid

ID_HEADER = 'X-Webhook-Id'
TIMESTAMP_HEADER = 'X-Webhook-Timestamp'
SIGNATURE_HEADER = 'X-Webhook-Signature'
SIGNATURE_PREFIX = 'sha256='


def compute_signature(secret: str, timestamp: int, body: bytes) -> str:
    """Return the signature header value for a request: 'sha256=<hex digest>'."""
    message = f'{timestamp}.'.encode() + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return f'{SIGNATURE_PREFIX}{digest}'


def build_signed_headers(secret: str, event_id: uuid.UUID, timestamp: int, body: bytes) -> dict[str, str]:
    """Return the headers to send with a webhook request.

    Args:
        secret: The endpoint's secret.
        event_id: Id of the event in the body.
        timestamp: Unix seconds at publish time.
        body: The exact bytes that will be sent.
    """
    return {
        'Content-Type': 'application/json',
        ID_HEADER: str(event_id),
        TIMESTAMP_HEADER: str(timestamp),
        SIGNATURE_HEADER: compute_signature(secret, timestamp, body),
    }


def verify_signature(secret: str, timestamp: int, body: bytes, signature: str) -> bool:
    """Check a signature header value the way a receiver should.

    Uses a constant-time comparison so the check does not leak how much of
    the signature matched.
    """
    expected_signature = compute_signature(secret, timestamp, body)
    return hmac.compare_digest(expected_signature, signature)

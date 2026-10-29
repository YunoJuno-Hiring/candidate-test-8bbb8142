"""
Webhook payload schema.

Every event is sent in the same versioned envelope:

    {
        "id": "<event uuid>",
        "type": "timesheet.approved",
        "version": 1,
        "created_at": "2026-10-28T17:00:00+00:00",
        "data": {...}
    }

The body is serialized once, when the event is published. Those exact bytes
are signed and sent on every attempt, so retries never change the payload.
"""

import datetime
import json
import uuid

from django.core.serializers.json import DjangoJSONEncoder

PAYLOAD_VERSION = 1


def build_event_body(
    event_id: uuid.UUID,
    event_type: str,
    created_at: datetime.datetime,
    data: dict,
) -> bytes:
    """Serialize an event into the bytes sent as the request body.

    Args:
        event_id: Unique id of the event; receivers dedupe on it.
        event_type: Dotted event name, e.g. 'timesheet.approved'.
        created_at: When the event happened. Must be timezone-aware; it is
            sent in UTC.
        data: Event-specific fields. Dates, datetimes, Decimals and UUIDs are
            encoded as strings.

    Returns:
        Compact UTF-8 JSON with sorted keys, so the same event always produces
        the same bytes.

    Raises:
        ValueError: If created_at is naive.
    """
    if created_at.tzinfo is None:
        raise ValueError('created_at must be timezone-aware')

    envelope = {
        'id': str(event_id),
        'type': event_type,
        'version': PAYLOAD_VERSION,
        'created_at': created_at.astimezone(datetime.UTC).isoformat(),
        'data': data,
    }
    return json.dumps(envelope, cls=DjangoJSONEncoder, separators=(',', ':'), sort_keys=True).encode()

import datetime
import json
import uuid
from decimal import Decimal

import pytest

from webhooks.payloads import PAYLOAD_VERSION, build_event_body

EVENT_ID = uuid.UUID('6f1c1d2e-3b4a-4c5d-8e9f-0a1b2c3d4e5f')
CREATED_AT = datetime.datetime(2026, 10, 28, 17, 0, tzinfo=datetime.UTC)


def test_body_contains_versioned_envelope():
    body = build_event_body(EVENT_ID, 'timesheet.approved', CREATED_AT, {'timesheet_id': 7})
    assert json.loads(body) == {
        'id': '6f1c1d2e-3b4a-4c5d-8e9f-0a1b2c3d4e5f',
        'type': 'timesheet.approved',
        'version': PAYLOAD_VERSION,
        'created_at': '2026-10-28T17:00:00+00:00',
        'data': {'timesheet_id': 7},
    }


def test_created_at_is_converted_to_utc():
    madrid_time = datetime.datetime(2026, 10, 28, 18, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
    body = build_event_body(EVENT_ID, 'webhook.test', madrid_time, {})
    assert json.loads(body)['created_at'] == '2026-10-28T17:00:00+00:00'


def test_naive_created_at_rejected():
    with pytest.raises(ValueError):
        build_event_body(EVENT_ID, 'webhook.test', datetime.datetime(2026, 10, 28, 17, 0), {})


def test_dates_and_decimals_are_encoded_as_strings():
    data = {'date': datetime.date(2026, 4, 7), 'hours': Decimal('8.00')}
    body = build_event_body(EVENT_ID, 'timesheet.approved', CREATED_AT, data)
    assert json.loads(body)['data'] == {'date': '2026-04-07', 'hours': '8.00'}


def test_same_event_produces_identical_bytes():
    first = build_event_body(EVENT_ID, 'webhook.test', CREATED_AT, {'b': 1, 'a': 2})
    second = build_event_body(EVENT_ID, 'webhook.test', CREATED_AT, {'a': 2, 'b': 1})
    assert first == second


def test_body_is_compact_json():
    body = build_event_body(EVENT_ID, 'webhook.test', CREATED_AT, {'a': 1})
    assert b' ' not in body

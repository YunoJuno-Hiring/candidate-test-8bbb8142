import json
import socket
import uuid

import pytest

from webhooks import delivery
from webhooks.delivery import TEST_EVENT_MESSAGE, deliver, send_test_event
from webhooks.models import (
    EVENT_TIMESHEET_APPROVED,
    EVENT_WEBHOOK_TEST,
    WebhookDelivery,
    WebhookEndpoint,
)
from webhooks.payloads import PAYLOAD_VERSION
from webhooks.signing import (
    ID_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    verify_signature,
)


@pytest.fixture
def receiver_endpoint(northstar, fake_receiver):
    return WebhookEndpoint.objects.create(url=fake_receiver.url, company=northstar)


def _closed_port_url() -> str:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    return f'http://127.0.0.1:{port}/hook'


# --- deliver ---

@pytest.mark.django_db
def test_deliver_posts_exact_body_with_verifiable_signature(receiver_endpoint, fake_receiver):
    event_id = uuid.uuid4()
    body = b'{"id":"x"}'

    deliver(receiver_endpoint, event_id, EVENT_TIMESHEET_APPROVED, body, timestamp=1_700_000_000, attempt=1)

    [received] = fake_receiver.requests
    assert received.path == '/hook'
    assert received.body == body
    assert received.headers['Content-Type'] == 'application/json'
    assert received.headers[ID_HEADER] == str(event_id)
    assert received.headers[TIMESTAMP_HEADER] == '1700000000'
    assert verify_signature(receiver_endpoint.secret, 1_700_000_000, body, received.headers[SIGNATURE_HEADER])


@pytest.mark.django_db
def test_deliver_records_successful_attempt(receiver_endpoint):
    event_id = uuid.uuid4()

    result = deliver(receiver_endpoint, event_id, EVENT_TIMESHEET_APPROVED, b'{}', timestamp=1, attempt=3)

    saved = WebhookDelivery.objects.get()
    assert saved == result
    assert saved.destination == receiver_endpoint
    assert saved.event_id == event_id
    assert saved.event_type == EVENT_TIMESHEET_APPROVED
    assert saved.attempt == 3
    assert saved.successful is True
    assert saved.reason == 'HTTP 200'


@pytest.mark.django_db
@pytest.mark.parametrize(('status_code', 'is_successful'), [(204, True), (400, False), (500, False)])
def test_deliver_treats_only_2xx_as_success(receiver_endpoint, fake_receiver, status_code, is_successful):
    fake_receiver.status_code = status_code

    result = deliver(receiver_endpoint, uuid.uuid4(), EVENT_TIMESHEET_APPROVED, b'{}', timestamp=1, attempt=1)

    assert result.successful is is_successful
    assert result.reason == f'HTTP {status_code}'


@pytest.mark.django_db
def test_deliver_does_not_follow_redirects(receiver_endpoint, fake_receiver):
    fake_receiver.status_code = 302
    fake_receiver.extra_headers = {'Location': f'{fake_receiver.url}/elsewhere'}

    result = deliver(receiver_endpoint, uuid.uuid4(), EVENT_TIMESHEET_APPROVED, b'{}', timestamp=1, attempt=1)

    assert result.successful is False
    assert result.reason == 'HTTP 302'
    assert len(fake_receiver.requests) == 1


@pytest.mark.django_db
def test_deliver_records_timeout(receiver_endpoint, fake_receiver, monkeypatch):
    monkeypatch.setattr(delivery, 'DELIVERY_TIMEOUT_SECONDS', 0.1)
    fake_receiver.delay_seconds = 0.5

    result = deliver(receiver_endpoint, uuid.uuid4(), EVENT_TIMESHEET_APPROVED, b'{}', timestamp=1, attempt=1)

    assert result.successful is False
    assert result.reason == 'timeout after 0.1s'


@pytest.mark.django_db
@pytest.mark.parametrize('url', [_closed_port_url(), 'http://does-not-exist.invalid/hook'])
def test_deliver_records_connection_failure(northstar, url):
    endpoint = WebhookEndpoint.objects.create(url=url, company=northstar)

    result = deliver(endpoint, uuid.uuid4(), EVENT_TIMESHEET_APPROVED, b'{}', timestamp=1, attempt=1)

    assert result.successful is False
    assert result.reason == 'connection failed'


# --- send_test_event ---

@pytest.mark.django_db
def test_send_test_event_sends_versioned_test_payload(receiver_endpoint, fake_receiver):
    result = send_test_event(receiver_endpoint)

    [received] = fake_receiver.requests
    payload = json.loads(received.body)
    assert payload['id'] == str(result.event_id)
    assert payload['type'] == EVENT_WEBHOOK_TEST
    assert payload['version'] == PAYLOAD_VERSION
    assert payload['data'] == {'message': TEST_EVENT_MESSAGE}
    assert received.headers[ID_HEADER] == str(result.event_id)
    assert result.event_type == EVENT_WEBHOOK_TEST
    assert result.attempt == 1
    assert result.successful is True


@pytest.mark.django_db
def test_send_test_event_uses_a_new_event_id_each_time(receiver_endpoint):
    first = send_test_event(receiver_endpoint)
    second = send_test_event(receiver_endpoint)

    assert first.event_id != second.event_id
    assert WebhookDelivery.objects.count() == 2

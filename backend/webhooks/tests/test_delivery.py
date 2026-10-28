import json
import socket
import uuid

import pytest
from django.contrib.auth.models import User

from accounts.models import Freelancer
from webhooks import delivery
from webhooks.delivery import (
    TEST_EVENT_MESSAGE,
    deliver,
    publish_event,
    send_test_event,
)
from webhooks.models import (
    EVENT_CONTRACT_CREATED,
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


# --- publish_event ---

@pytest.mark.django_db
def test_publish_event_sends_signed_payload_to_subscribed_endpoints(northstar, fake_receiver):
    subscribed = WebhookEndpoint.objects.create(
        url=fake_receiver.url, company=northstar, event_types=[EVENT_TIMESHEET_APPROVED]
    )
    WebhookEndpoint.objects.create(
        url='http://127.0.0.1:9/other', company=northstar, event_types=[EVENT_CONTRACT_CREATED]
    )

    deliveries = publish_event(northstar, EVENT_TIMESHEET_APPROVED, {'timesheet_id': 7})

    assert len(deliveries) == 1
    assert deliveries[0].destination == subscribed
    assert deliveries[0].event_type == EVENT_TIMESHEET_APPROVED
    assert deliveries[0].successful is True
    [received] = fake_receiver.requests
    payload = json.loads(received.body)
    assert payload['type'] == EVENT_TIMESHEET_APPROVED
    assert payload['version'] == PAYLOAD_VERSION
    assert payload['data'] == {'timesheet_id': 7}
    assert received.headers[ID_HEADER] == str(deliveries[0].event_id)
    assert verify_signature(
        subscribed.secret,
        int(received.headers[TIMESTAMP_HEADER]),
        received.body,
        received.headers[SIGNATURE_HEADER],
    )


@pytest.mark.django_db
def test_publish_event_skips_inactive_endpoints(northstar, fake_receiver):
    WebhookEndpoint.objects.create(url=fake_receiver.url, company=northstar, active=False)

    deliveries = publish_event(northstar, EVENT_TIMESHEET_APPROVED, {'timesheet_id': 1})

    assert deliveries == []
    assert fake_receiver.requests == []


@pytest.mark.django_db
def test_publish_event_reuses_same_body_and_event_id_for_all_endpoints(northstar, fake_receiver):
    base = fake_receiver.url.rsplit('/', 1)[0]
    endpoints = {
        '/hook-a': WebhookEndpoint.objects.create(url=f'{base}/hook-a', company=northstar),
        '/hook-b': WebhookEndpoint.objects.create(url=f'{base}/hook-b', company=northstar),
    }

    deliveries = publish_event(northstar, EVENT_TIMESHEET_APPROVED, {'timesheet_id': 7})

    assert {d.destination_id for d in deliveries} == {ep.id for ep in endpoints.values()}
    assert deliveries[0].event_id == deliveries[1].event_id
    assert len(fake_receiver.requests) == 2
    assert fake_receiver.requests[0].body == fake_receiver.requests[1].body
    for received in fake_receiver.requests:
        endpoint = endpoints[received.path]
        assert verify_signature(
            endpoint.secret,
            int(received.headers[TIMESTAMP_HEADER]),
            received.body,
            received.headers[SIGNATURE_HEADER],
        )


@pytest.mark.django_db
def test_creating_contract_publishes_signed_webhook(admin_client, northstar, fake_receiver):
    endpoint = WebhookEndpoint.objects.create(url=fake_receiver.url, company=northstar)
    freelancer_user = User.objects.create_user(
        username='hooked@test.test', email='hooked@test.test', password='x'
    )
    freelancer = Freelancer.objects.create(user=freelancer_user, name='Hooked Freelancer')

    resp = admin_client.post(
        '/api/contracts/',
        {
            'freelancer': freelancer.id,
            'daily_rate': '550.00',
            'start_date': '2026-02-01',
            'end_date': '2026-08-31',
            'status': 'active',
        },
        format='json',
    )

    assert resp.status_code == 201
    delivery = WebhookDelivery.objects.get()
    assert delivery.event_type == EVENT_CONTRACT_CREATED
    assert delivery.destination == endpoint
    assert delivery.successful is True
    [received] = fake_receiver.requests
    payload = json.loads(received.body)
    assert payload['type'] == EVENT_CONTRACT_CREATED
    assert payload['data'] == {
        'contract_id': resp.data['id'],
        'freelancer_id': freelancer.id,
        'daily_rate': '550.00',
        'start_date': '2026-02-01',
        'end_date': '2026-08-31',
        'status': 'active',
    }
    assert received.headers[ID_HEADER] == str(delivery.event_id)
    assert verify_signature(
        endpoint.secret,
        int(received.headers[TIMESTAMP_HEADER]),
        received.body,
        received.headers[SIGNATURE_HEADER],
    )


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

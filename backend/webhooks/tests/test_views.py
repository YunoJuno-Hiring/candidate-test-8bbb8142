import uuid

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import CompanyAdmin
from webhooks.models import (
    EVENT_CONTRACT_CREATED,
    EVENT_TIMESHEET_APPROVED,
    WebhookDelivery,
    WebhookEndpoint,
)
from webhooks.serializers import (
    DUPLICATE_URL_MESSAGE,
    RECENT_DELIVERIES_LIMIT,
    WebhookEndpointSerializer,
)

LIST_URL = '/api/webhook-endpoints/'


def _detail_url(endpoint_id: int) -> str:
    return f'/api/webhook-endpoints/{endpoint_id}/'


@pytest.fixture
def endpoint(northstar, admin_user):
    return WebhookEndpoint.objects.create(
        url='https://northstar.test/hooks', company=northstar, created_by=admin_user
    )


@pytest.fixture
def other_endpoint(meridian):
    return WebhookEndpoint.objects.create(url='https://meridian.test/hooks', company=meridian)


@pytest.fixture
def second_admin_client(northstar):
    user = User.objects.create_user(
        username='second-admin@test.test', email='second-admin@test.test', password='testpass'
    )
    CompanyAdmin.objects.create(user=user, company=northstar)
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def _test_url(endpoint_id: int) -> str:
    return f'/api/webhook-endpoints/{endpoint_id}/test/'


def _send(client, method: str, target: str, endpoint_id: int):
    if target == 'list':
        return getattr(client, method)(LIST_URL, {'url': 'https://new.test/hooks'}, format='json')
    if target == 'test':
        return client.post(_test_url(endpoint_id), format='json')
    return getattr(client, method)(_detail_url(endpoint_id), {'active': False}, format='json')


def _create_delivery(endpoint: WebhookEndpoint, attempt: int = 1, **fields) -> WebhookDelivery:
    return WebhookDelivery.objects.create(
        event_id=fields.pop('event_id', uuid.uuid4()),
        event_type='timesheet.approved',
        destination=endpoint,
        attempt=attempt,
        successful=fields.pop('successful', True),
        **fields,
    )


ALL_ROUTES = [
    ('get', 'list'),
    ('post', 'list'),
    ('get', 'detail'),
    ('patch', 'detail'),
    ('delete', 'detail'),
    ('post', 'test'),
]


# --- Access rules shared by every endpoint ---

@pytest.mark.django_db
@pytest.mark.parametrize(('method', 'target'), ALL_ROUTES)
def test_webhook_endpoints_require_auth(api_client, endpoint, method, target):
    resp = _send(api_client, method, target, endpoint.id)
    assert resp.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize(('method', 'target'), ALL_ROUTES)
def test_freelancer_cannot_manage_webhook_endpoints(freelancer_client, endpoint, method, target):
    resp = _send(freelancer_client, method, target, endpoint.id)

    assert resp.status_code == 403
    endpoint.refresh_from_db()
    assert endpoint.active is True
    assert WebhookEndpoint.objects.count() == 1
    assert not WebhookDelivery.objects.exists()


# --- List ---

@pytest.mark.django_db
def test_admin_lists_only_own_company_endpoints(admin_client, endpoint, other_endpoint):
    resp = admin_client.get(LIST_URL)

    assert resp.status_code == 200
    assert [item['id'] for item in resp.data] == [endpoint.id]


@pytest.mark.django_db
def test_list_does_not_expose_secret(admin_client, endpoint):
    resp = admin_client.get(LIST_URL)
    assert 'secret' not in resp.data[0]


# --- Create ---

@pytest.mark.django_db
def test_admin_creates_endpoint_and_receives_secret(admin_client, admin_user, northstar):
    resp = admin_client.post(LIST_URL, {'url': 'https://new.test/hooks'}, format='json')

    assert resp.status_code == 201
    created = WebhookEndpoint.objects.get(pk=resp.data['id'])
    assert resp.data['secret'] == created.secret
    assert resp.data['url'] == 'https://new.test/hooks'
    assert resp.data['active'] is True
    assert created.company == northstar
    assert created.created_by == admin_user


@pytest.mark.django_db
def test_create_without_event_types_subscribes_to_all(admin_client):
    resp = admin_client.post(LIST_URL, {'url': 'https://new.test/hooks'}, format='json')

    assert resp.status_code == 201
    assert resp.data['event_types'] == []


@pytest.mark.django_db
def test_create_stores_event_types_deduplicated_and_sorted(admin_client):
    resp = admin_client.post(
        LIST_URL,
        {
            'url': 'https://new.test/hooks',
            'event_types': [EVENT_TIMESHEET_APPROVED, EVENT_CONTRACT_CREATED, EVENT_TIMESHEET_APPROVED],
        },
        format='json',
    )

    assert resp.status_code == 201
    assert resp.data['event_types'] == [EVENT_CONTRACT_CREATED, EVENT_TIMESHEET_APPROVED]
    created = WebhookEndpoint.objects.get(pk=resp.data['id'])
    assert created.event_types == [EVENT_CONTRACT_CREATED, EVENT_TIMESHEET_APPROVED]


@pytest.mark.django_db
@pytest.mark.parametrize('event_types', [['invoice.paid'], ['webhook.test'], EVENT_TIMESHEET_APPROVED, None])
def test_create_rejects_invalid_event_types(admin_client, event_types):
    resp = admin_client.post(
        LIST_URL, {'url': 'https://new.test/hooks', 'event_types': event_types}, format='json'
    )

    assert resp.status_code == 400
    assert 'event_types' in resp.data
    assert not WebhookEndpoint.objects.exists()


@pytest.mark.django_db
def test_create_ignores_company_and_secret_from_body(admin_client, northstar, meridian):
    resp = admin_client.post(
        LIST_URL,
        {'url': 'https://new.test/hooks', 'company': meridian.id, 'secret': 'chosen-by-client'},
        format='json',
    )

    assert resp.status_code == 201
    created = WebhookEndpoint.objects.get(pk=resp.data['id'])
    assert created.company == northstar
    assert created.secret != 'chosen-by-client'


@pytest.mark.django_db
def test_create_accepts_local_receiver_url(admin_client):
    resp = admin_client.post(LIST_URL, {'url': 'http://webhook-receiver:8027/hook'}, format='json')
    assert resp.status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize(
    'url',
    [
        '',
        'not a url',
        'ftp://files.test/hooks',
        'https://',
        'https://bad host.test/hooks',
        'https://host.test:port/hooks',
        'https://host.test:0/hooks',
    ],
)
def test_create_rejects_invalid_url(admin_client, url):
    resp = admin_client.post(LIST_URL, {'url': url}, format='json')

    assert resp.status_code == 400
    assert 'url' in resp.data
    assert not WebhookEndpoint.objects.exists()


@pytest.mark.django_db
def test_create_rejects_url_already_registered_by_same_company(admin_client, endpoint):
    resp = admin_client.post(LIST_URL, {'url': endpoint.url}, format='json')

    assert resp.status_code == 400
    assert resp.data['url'] == [DUPLICATE_URL_MESSAGE]
    assert WebhookEndpoint.objects.count() == 1


@pytest.mark.django_db
def test_create_allows_url_registered_by_other_company(admin_client, northstar, other_endpoint):
    resp = admin_client.post(LIST_URL, {'url': other_endpoint.url}, format='json')

    assert resp.status_code == 201
    created = WebhookEndpoint.objects.get(pk=resp.data['id'])
    assert created.company == northstar
    assert created.secret != other_endpoint.secret


@pytest.mark.django_db
def test_create_returns_400_when_concurrent_request_took_url(admin_client, endpoint, monkeypatch):
    monkeypatch.setattr(WebhookEndpointSerializer, '_is_url_taken', lambda self, url: False)

    resp = admin_client.post(LIST_URL, {'url': endpoint.url}, format='json')

    assert resp.status_code == 400
    assert resp.data['url'] == [DUPLICATE_URL_MESSAGE]
    assert WebhookEndpoint.objects.count() == 1


# --- Detail ---

@pytest.mark.django_db
def test_admin_gets_own_company_endpoint_without_secret(admin_client, endpoint):
    resp = admin_client.get(_detail_url(endpoint.id))

    assert resp.status_code == 200
    assert resp.data['id'] == endpoint.id
    assert resp.data['url'] == endpoint.url
    assert resp.data['deliveries'] == []
    assert 'secret' not in resp.data


@pytest.mark.django_db
def test_detail_lists_deliveries_newest_first(admin_client, endpoint):
    event_id = uuid.uuid4()
    first = _create_delivery(endpoint, attempt=1, event_id=event_id, successful=False, reason='HTTP 500')
    retry = _create_delivery(endpoint, attempt=2, event_id=event_id)

    resp = admin_client.get(_detail_url(endpoint.id))

    deliveries = resp.data['deliveries']
    assert [d['id'] for d in deliveries] == [retry.id, first.id]
    assert deliveries[1]['event_id'] == str(event_id)
    assert deliveries[1]['successful'] is False
    assert deliveries[1]['reason'] == 'HTTP 500'


@pytest.mark.django_db
def test_detail_excludes_other_endpoint_deliveries(admin_client, endpoint, northstar):
    sibling = WebhookEndpoint.objects.create(url='https://sibling.test/hooks', company=northstar)
    _create_delivery(sibling)

    resp = admin_client.get(_detail_url(endpoint.id))
    assert resp.data['deliveries'] == []


@pytest.mark.django_db
def test_detail_caps_deliveries_to_most_recent(admin_client, endpoint):
    for attempt in range(1, RECENT_DELIVERIES_LIMIT + 2):
        _create_delivery(endpoint, attempt=attempt)

    resp = admin_client.get(_detail_url(endpoint.id))

    attempts = [d['attempt'] for d in resp.data['deliveries']]
    assert len(attempts) == RECENT_DELIVERIES_LIMIT
    assert 1 not in attempts


@pytest.mark.django_db
def test_admin_cannot_get_other_company_endpoint(admin_client, other_endpoint):
    _create_delivery(other_endpoint)

    resp = admin_client.get(_detail_url(other_endpoint.id))
    assert resp.status_code == 404


# --- Edit ---

@pytest.mark.django_db
def test_admin_edits_own_company_endpoint(admin_client, endpoint):
    original_secret = endpoint.secret

    resp = admin_client.patch(
        _detail_url(endpoint.id), {'url': 'https://moved.test/hooks', 'active': False}, format='json'
    )

    assert resp.status_code == 200
    assert resp.data['url'] == 'https://moved.test/hooks'
    assert resp.data['active'] is False
    assert 'secret' not in resp.data
    endpoint.refresh_from_db()
    assert endpoint.url == 'https://moved.test/hooks'
    assert endpoint.active is False
    assert endpoint.secret == original_secret


@pytest.mark.django_db
def test_edit_changes_event_types(admin_client, endpoint):
    resp = admin_client.patch(
        _detail_url(endpoint.id), {'event_types': [EVENT_CONTRACT_CREATED]}, format='json'
    )

    assert resp.status_code == 200
    assert resp.data['event_types'] == [EVENT_CONTRACT_CREATED]
    endpoint.refresh_from_db()
    assert endpoint.event_types == [EVENT_CONTRACT_CREATED]


@pytest.mark.django_db
def test_edit_with_empty_event_types_subscribes_to_all(admin_client, endpoint):
    endpoint.event_types = [EVENT_CONTRACT_CREATED]
    endpoint.save()

    resp = admin_client.patch(_detail_url(endpoint.id), {'event_types': []}, format='json')

    assert resp.status_code == 200
    endpoint.refresh_from_db()
    assert endpoint.event_types == []


@pytest.mark.django_db
def test_edit_without_event_types_keeps_them(admin_client, endpoint):
    endpoint.event_types = [EVENT_CONTRACT_CREATED]
    endpoint.save()

    resp = admin_client.patch(_detail_url(endpoint.id), {'active': False}, format='json')

    assert resp.status_code == 200
    endpoint.refresh_from_db()
    assert endpoint.event_types == [EVENT_CONTRACT_CREATED]


@pytest.mark.django_db
def test_any_admin_of_the_company_can_edit_endpoint(second_admin_client, endpoint):
    resp = second_admin_client.patch(_detail_url(endpoint.id), {'active': False}, format='json')

    assert resp.status_code == 200
    endpoint.refresh_from_db()
    assert endpoint.active is False


@pytest.mark.django_db
def test_admin_cannot_edit_other_company_endpoint(admin_client, other_endpoint):
    resp = admin_client.patch(_detail_url(other_endpoint.id), {'active': False}, format='json')

    assert resp.status_code == 404
    other_endpoint.refresh_from_db()
    assert other_endpoint.active is True


@pytest.mark.django_db
def test_edit_ignores_company_and_secret_from_body(admin_client, endpoint, northstar, meridian):
    original_secret = endpoint.secret

    resp = admin_client.patch(
        _detail_url(endpoint.id), {'company': meridian.id, 'secret': 'chosen-by-client'}, format='json'
    )

    assert resp.status_code == 200
    endpoint.refresh_from_db()
    assert endpoint.company == northstar
    assert endpoint.secret == original_secret


@pytest.mark.django_db
def test_edit_rejects_invalid_url(admin_client, endpoint):
    resp = admin_client.patch(_detail_url(endpoint.id), {'url': 'not a url'}, format='json')

    assert resp.status_code == 400
    endpoint.refresh_from_db()
    assert endpoint.url == 'https://northstar.test/hooks'


@pytest.mark.django_db
def test_edit_rejects_url_of_another_endpoint_in_same_company(admin_client, endpoint, northstar):
    sibling = WebhookEndpoint.objects.create(url='https://sibling.test/hooks', company=northstar)

    resp = admin_client.patch(_detail_url(endpoint.id), {'url': sibling.url}, format='json')

    assert resp.status_code == 400
    assert resp.data['url'] == [DUPLICATE_URL_MESSAGE]
    endpoint.refresh_from_db()
    assert endpoint.url == 'https://northstar.test/hooks'


@pytest.mark.django_db
def test_edit_allows_url_registered_by_other_company(admin_client, endpoint, other_endpoint):
    resp = admin_client.patch(_detail_url(endpoint.id), {'url': other_endpoint.url}, format='json')
    assert resp.status_code == 200


@pytest.mark.django_db
def test_edit_keeping_same_url_is_not_a_duplicate(admin_client, endpoint):
    resp = admin_client.patch(_detail_url(endpoint.id), {'url': endpoint.url}, format='json')
    assert resp.status_code == 200


@pytest.mark.django_db
def test_edit_missing_endpoint_returns_404(admin_client):
    resp = admin_client.patch(_detail_url(999999), {'active': False}, format='json')
    assert resp.status_code == 404


# --- Delete ---

@pytest.mark.django_db
def test_admin_deletes_own_company_endpoint(admin_client, endpoint):
    resp = admin_client.delete(_detail_url(endpoint.id))

    assert resp.status_code == 204
    assert not WebhookEndpoint.objects.filter(pk=endpoint.id).exists()


@pytest.mark.django_db
def test_admin_cannot_delete_other_company_endpoint(admin_client, other_endpoint):
    resp = admin_client.delete(_detail_url(other_endpoint.id))

    assert resp.status_code == 404
    assert WebhookEndpoint.objects.filter(pk=other_endpoint.id).exists()


# --- Send test event ---

@pytest.mark.django_db
def test_admin_sends_test_event_and_gets_logged_delivery(admin_client, northstar, fake_receiver):
    endpoint = WebhookEndpoint.objects.create(url=fake_receiver.url, company=northstar)

    resp = admin_client.post(_test_url(endpoint.id), format='json')

    assert resp.status_code == 201
    assert resp.data['event_type'] == 'webhook.test'
    assert resp.data['attempt'] == 1
    assert resp.data['successful'] is True
    assert resp.data['reason'] == 'HTTP 200'
    assert len(fake_receiver.requests) == 1
    detail = admin_client.get(_detail_url(endpoint.id))
    assert [d['id'] for d in detail.data['deliveries']] == [resp.data['id']]


@pytest.mark.django_db
def test_failed_test_event_is_reported_not_raised(admin_client, northstar, fake_receiver):
    fake_receiver.status_code = 500
    endpoint = WebhookEndpoint.objects.create(url=fake_receiver.url, company=northstar)

    resp = admin_client.post(_test_url(endpoint.id), format='json')

    assert resp.status_code == 201
    assert resp.data['successful'] is False
    assert resp.data['reason'] == 'HTTP 500'


@pytest.mark.django_db
def test_test_event_is_sent_to_disabled_endpoint(admin_client, northstar, fake_receiver):
    endpoint = WebhookEndpoint.objects.create(url=fake_receiver.url, company=northstar, active=False)

    resp = admin_client.post(_test_url(endpoint.id), format='json')

    assert resp.status_code == 201
    assert len(fake_receiver.requests) == 1


@pytest.mark.django_db
def test_admin_cannot_send_test_event_to_other_company_endpoint(admin_client, meridian, fake_receiver):
    endpoint = WebhookEndpoint.objects.create(url=fake_receiver.url, company=meridian)

    resp = admin_client.post(_test_url(endpoint.id), format='json')

    assert resp.status_code == 404
    assert fake_receiver.requests == []
    assert not WebhookDelivery.objects.exists()

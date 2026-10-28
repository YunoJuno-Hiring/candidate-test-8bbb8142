import uuid

import pytest
from django.db import IntegrityError

from webhooks.models import WebhookDelivery, WebhookEndpoint


@pytest.fixture
def endpoint(northstar, admin_user):
    return WebhookEndpoint.objects.create(
        url='https://example.test/hooks', company=northstar, created_by=admin_user
    )


@pytest.mark.django_db
def test_endpoint_defaults_to_active(endpoint):
    assert endpoint.active is True


@pytest.mark.django_db
def test_secret_is_generated_on_create(endpoint):
    assert len(endpoint.secret) == 64
    int(endpoint.secret, 16)


@pytest.mark.django_db
def test_each_endpoint_gets_a_different_secret(endpoint, northstar):
    other = WebhookEndpoint.objects.create(url='https://example.test/other', company=northstar)
    assert other.secret != endpoint.secret


@pytest.mark.django_db
def test_secret_is_kept_when_endpoint_is_updated(endpoint):
    original_secret = endpoint.secret
    endpoint.active = False
    endpoint.save()
    endpoint.refresh_from_db()
    assert endpoint.secret == original_secret


@pytest.mark.django_db
def test_last_modified_changes_on_save(endpoint):
    original_last_modified = endpoint.last_modified
    endpoint.url = 'https://example.test/new'
    endpoint.save()
    assert endpoint.last_modified > original_last_modified
    assert endpoint.created_at < endpoint.last_modified


@pytest.mark.django_db
def test_duplicate_url_for_same_company_rejected(endpoint, northstar):
    with pytest.raises(IntegrityError):
        WebhookEndpoint.objects.create(url=endpoint.url, company=northstar)


@pytest.mark.django_db
def test_duplicate_url_for_different_company_rejected(endpoint, meridian):
    with pytest.raises(IntegrityError):
        WebhookEndpoint.objects.create(url=endpoint.url, company=meridian)


@pytest.mark.django_db
def test_endpoint_survives_deletion_of_its_creator(endpoint, admin_user):
    admin_user.delete()
    endpoint.refresh_from_db()
    assert endpoint.created_by is None


@pytest.fixture
def delivery(endpoint):
    return WebhookDelivery.objects.create(
        event_id=uuid.uuid4(), event_type='webhook.test', destination=endpoint, attempt=1, successful=False
    )


@pytest.mark.django_db
def test_each_retry_adds_a_new_log_entry(delivery, endpoint):
    WebhookDelivery.objects.create(
        event_id=delivery.event_id, event_type='webhook.test', destination=endpoint, attempt=2, successful=True
    )
    history = WebhookDelivery.objects.filter(event_id=delivery.event_id).order_by('attempt')
    assert [(entry.attempt, entry.successful) for entry in history] == [(1, False), (2, True)]


@pytest.mark.django_db
def test_same_attempt_cannot_be_logged_twice(delivery, endpoint):
    with pytest.raises(IntegrityError):
        WebhookDelivery.objects.create(
            event_id=delivery.event_id, event_type='webhook.test', destination=endpoint, attempt=1, successful=True
        )


@pytest.mark.django_db
def test_same_event_and_attempt_allowed_for_different_destinations(delivery, northstar):
    other_endpoint = WebhookEndpoint.objects.create(url='https://example.test/other', company=northstar)
    other = WebhookDelivery.objects.create(
        event_id=delivery.event_id, event_type='webhook.test', destination=other_endpoint, attempt=1, successful=True
    )
    assert other.event_id == delivery.event_id


@pytest.mark.django_db
def test_attempt_zero_rejected(endpoint):
    with pytest.raises(IntegrityError):
        WebhookDelivery.objects.create(
            event_id=uuid.uuid4(), event_type='webhook.test', destination=endpoint, attempt=0, successful=True
        )


@pytest.mark.django_db
def test_reason_is_optional(delivery):
    assert delivery.reason == ''


@pytest.mark.django_db
def test_failed_attempt_records_its_reason(endpoint):
    delivery = WebhookDelivery.objects.create(
        event_id=uuid.uuid4(),
        event_type='webhook.test',
        destination=endpoint,
        attempt=1,
        successful=False,
        reason='timeout after 10s',
    )
    delivery.refresh_from_db()
    assert delivery.reason == 'timeout after 10s'


@pytest.mark.django_db
def test_successful_must_be_set(endpoint):
    with pytest.raises(IntegrityError):
        WebhookDelivery.objects.create(event_id=uuid.uuid4(), event_type='webhook.test', destination=endpoint, attempt=1)


@pytest.mark.django_db
def test_deliveries_are_deleted_with_their_endpoint(delivery, endpoint):
    endpoint.delete()
    assert not WebhookDelivery.objects.filter(pk=delivery.pk).exists()

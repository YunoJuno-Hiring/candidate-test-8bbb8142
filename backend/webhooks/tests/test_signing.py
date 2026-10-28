import uuid

import pytest

from webhooks.signing import (
    ID_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    build_signed_headers,
    compute_signature,
    verify_signature,
)

SECRET = 'test-secret'
TIMESTAMP = 1700000000
BODY = b'{"hello":"world"}'


def test_signature_matches_known_vector():
    assert compute_signature(SECRET, TIMESTAMP, BODY) == (
        'sha256=f85455a1b55ea86f7a15f5f9923d0abc4b888da84ec485f2ff358f427776beca'
    )


def test_headers_carry_event_id_timestamp_and_signature():
    event_id = uuid.uuid4()
    headers = build_signed_headers(SECRET, event_id, TIMESTAMP, BODY)
    assert headers['Content-Type'] == 'application/json'
    assert headers[ID_HEADER] == str(event_id)
    assert headers[TIMESTAMP_HEADER] == str(TIMESTAMP)
    assert headers[SIGNATURE_HEADER] == compute_signature(SECRET, TIMESTAMP, BODY)


def test_valid_signature_is_accepted():
    signature = compute_signature(SECRET, TIMESTAMP, BODY)
    assert verify_signature(SECRET, TIMESTAMP, BODY, signature) is True


@pytest.mark.parametrize(
    'secret, timestamp, body',
    [
        ('other-secret', TIMESTAMP, BODY),
        (SECRET, TIMESTAMP + 1, BODY),
        (SECRET, TIMESTAMP, b'{"hello":"world!"}'),
    ],
    ids=['wrong_secret', 'changed_timestamp', 'changed_body'],
)
def test_signature_rejected_when_anything_changes(secret, timestamp, body):
    signature = compute_signature(SECRET, TIMESTAMP, BODY)
    assert verify_signature(secret, timestamp, body, signature) is False


@pytest.mark.parametrize(
    'signature',
    ['', 'f85455a1b55ea86f7a15f5f9923d0abc4b888da84ec485f2ff358f427776beca', 'sha256=deadbeef'],
    ids=['empty', 'missing_prefix', 'wrong_digest'],
)
def test_malformed_signature_rejected(signature):
    assert verify_signature(SECRET, TIMESTAMP, BODY, signature) is False

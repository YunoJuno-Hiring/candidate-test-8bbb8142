from urllib.parse import SplitResult, urlsplit

from rest_framework import serializers

from .models import EVENT_TYPE_CHOICES, WebhookDelivery, WebhookEndpoint

ALLOWED_URL_SCHEMES = ('http', 'https')
RECENT_DELIVERIES_LIMIT = 50
DUPLICATE_URL_MESSAGE = 'This URL is already registered for your company.'


def _has_valid_port(parts: SplitResult) -> bool:
    try:
        return parts.port is None or parts.port > 0
    except ValueError:
        return False


def _is_valid_webhook_url(value: str) -> bool:
    """Return True for an http(s) URL with a host and, if present, a valid port."""
    if any(char.isspace() for char in value):
        return False
    parts = urlsplit(value)
    return parts.scheme in ALLOWED_URL_SCHEMES and bool(parts.hostname) and _has_valid_port(parts)


class WebhookEndpointSerializer(serializers.ModelSerializer):
    """Reads and edits an endpoint; the secret is never part of this output.

    The URL is checked by hand instead of with Django's URLValidator, which
    rejects single-label hosts such as the local `webhook-receiver` container.
    URLs are unique per company; creating an endpoint requires the admin's
    company in the serializer context as `company`.
    """

    url = serializers.CharField(max_length=2048)
    # Empty, or left out on create, subscribes the endpoint to every event type.
    event_types = serializers.ListField(
        child=serializers.ChoiceField(choices=EVENT_TYPE_CHOICES), required=False, allow_empty=True
    )

    class Meta:
        model = WebhookEndpoint
        fields = ['id', 'url', 'active', 'event_types', 'created_at', 'last_modified']
        read_only_fields = ['id', 'created_at', 'last_modified']

    def validate_event_types(self, value):
        return sorted(set(value))

    def validate_url(self, value):
        if not _is_valid_webhook_url(value):
            raise serializers.ValidationError('Enter a valid http or https URL.')
        if self._is_url_taken(value):
            raise serializers.ValidationError(DUPLICATE_URL_MESSAGE)
        return value

    def _is_url_taken(self, url: str) -> bool:
        if self.instance is not None:
            others = WebhookEndpoint.objects.filter(company_id=self.instance.company_id).exclude(
                pk=self.instance.pk
            )
        else:
            others = WebhookEndpoint.objects.filter(company=self.context['company'])
        return others.filter(url=url).exists()


class WebhookEndpointCreateSerializer(WebhookEndpointSerializer):
    """Used only for the create response: the one time the secret is returned,
    so the receiver can store it and verify signatures."""

    class Meta(WebhookEndpointSerializer.Meta):
        fields = [*WebhookEndpointSerializer.Meta.fields, 'secret']
        read_only_fields = [*WebhookEndpointSerializer.Meta.read_only_fields, 'secret']


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = ['id', 'event_id', 'event_type', 'attempt', 'successful', 'reason', 'created_at']
        read_only_fields = fields


class WebhookEndpointDetailSerializer(WebhookEndpointSerializer):
    """An endpoint with its most recent delivery attempts, newest first."""

    deliveries = serializers.SerializerMethodField()

    class Meta(WebhookEndpointSerializer.Meta):
        fields = [*WebhookEndpointSerializer.Meta.fields, 'deliveries']

    def get_deliveries(self, obj):
        # TODO: move to a paginated deliveries endpoint once the log page needs older history.
        qs = obj.deliveries.order_by('-created_at', '-id')[:RECENT_DELIVERIES_LIMIT]
        return WebhookDeliverySerializer(qs, many=True).data

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .delivery import send_test_event
from .models import UNIQUE_COMPANY_URL_CONSTRAINT, WebhookEndpoint
from .serializers import (
    DUPLICATE_URL_MESSAGE,
    WebhookDeliverySerializer,
    WebhookEndpointCreateSerializer,
    WebhookEndpointDetailSerializer,
    WebhookEndpointSerializer,
)


class IsCompanyAdmin(BasePermission):
    message = 'Only company admins can manage webhook endpoints.'

    def has_permission(self, request, view):
        return hasattr(request.user, 'company_admin')


def _save_endpoint(serializer: WebhookEndpointSerializer, **fields) -> None:
    """Save the endpoint, answering 400 if a concurrent request took the URL.

    The serializer already rejects duplicates; this covers two requests that
    both pass that check before either one is saved.
    """
    try:
        with transaction.atomic():
            serializer.save(**fields)
    except IntegrityError as exc:
        if UNIQUE_COMPANY_URL_CONSTRAINT not in str(exc):
            raise
        raise serializers.ValidationError({'url': [DUPLICATE_URL_MESSAGE]}) from exc


class WebhookEndpointListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request):
        qs = WebhookEndpoint.objects.filter(company_id=request.user.company_admin.company_id)
        return Response(WebhookEndpointSerializer(qs, many=True).data)

    def post(self, request):
        # The company is taken from the admin, never trusted from the request body.
        company = request.user.company_admin.company
        serializer = WebhookEndpointCreateSerializer(data=request.data, context={'company': company})
        serializer.is_valid(raise_exception=True)
        _save_endpoint(serializer, company=company, created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WebhookEndpointDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, pk):
        endpoint = self._get_endpoint(request, pk)
        return Response(WebhookEndpointDetailSerializer(endpoint).data)

    def patch(self, request, pk):
        endpoint = self._get_endpoint(request, pk)
        serializer = WebhookEndpointSerializer(endpoint, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_endpoint(serializer)
        return Response(serializer.data)

    def delete(self, request, pk):
        self._get_endpoint(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _get_endpoint(self, request, pk):
        return _get_company_endpoint(request, pk)


class WebhookEndpointTestView(APIView):
    """Sends one test event to the endpoint and returns the recorded delivery.

    Delivery is synchronous, so the admin sees the receiver's answer at once.
    A failed delivery is still a 201: the attempt was made and logged, and
    its outcome is in the response body.
    """

    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def post(self, request, pk):
        delivery = send_test_event(_get_company_endpoint(request, pk))
        return Response(WebhookDeliverySerializer(delivery).data, status=status.HTTP_201_CREATED)

def _get_company_endpoint(request, pk) -> WebhookEndpoint:
    # Another company's endpoint gives 404, so its existence is not revealed.
    return get_object_or_404(WebhookEndpoint, pk=pk, company_id=request.user.company_admin.company_id)


class IsDeliveryServiceStub(BasePermission):
    """Lets in only the delivery service, by its shared token."""

    message = 'Only the webhook delivery service can report deliveries.'

    def has_permission(self, request, view):
        ...


class WebhookDeliveryReportViewStub(APIView):
    """Stub for a future design: not implemented yet, always answers 501.

    Planned async flow: publishing an event signs the request for each
    subscribed endpoint and enqueues it (URL, signed headers, body, endpoint
    id, attempt) instead of POSTing inline. A worker consuming that queue
    sends those exact bytes, then reports the outcome here before acking the
    message, and re-enqueues with a backoff and attempt + 1 when it failed.
    The worker never holds endpoint secrets.

    Planned contract, one report per attempt:

        {"event_id", "event_type", "destination", "attempt", "successful", "reason"}

    Queues deliver at least once, so reports must be idempotent on
    (event_id, destination, attempt), which the WebhookDelivery unique
    constraint already enforces:
        201  new attempt recorded; ack.
        200  same attempt already recorded with the same outcome; ack.
        409  same attempt already recorded with a different outcome; the log
             is append-only, so the stored row wins.
        400  invalid report, or the endpoint was deleted; drop the message.
        5xx  not recorded; do not ack, the queue redelivers.
    """

    authentication_classes = []
    permission_classes = [IsDeliveryServiceStub]

    def post(self, request):
        ...

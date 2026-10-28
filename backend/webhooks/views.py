from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UNIQUE_COMPANY_URL_CONSTRAINT, WebhookEndpoint
from .serializers import (
    DUPLICATE_URL_MESSAGE,
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
        # Another company's endpoint gives 404, so its existence is not revealed.
        return get_object_or_404(
            WebhookEndpoint, pk=pk, company_id=request.user.company_admin.company_id
        )

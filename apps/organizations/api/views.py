from django_filters.rest_framework import DjangoFilterBackend
from organizations.api.serializers import OrganizationSerializer
from organizations.models import Organization
from organizations.services.organization_creation import (
    create_organization_with_verification,
)
from rest_framework import status
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.services.pii import build_lookup_hash


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.select_related("owner", "business_license_image")
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = [
        "status",
        "verification_status",
        "name",
        "trade_name",
    ]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()

        queryset = self.queryset.filter(owner=self.request.user)
        params = getattr(self.request, "query_params", self.request.GET)
        if params.get("tin_number"):
            lookup_hash = build_lookup_hash(
                params["tin_number"],
                context="organizations.organization.tin_number",
            )
            queryset = queryset.filter(tin_number_lookup_hash=lookup_hash)
        if params.get("license_no"):
            lookup_hash = build_lookup_hash(
                params["license_no"],
                context="organizations.organization.license_no",
            )
            queryset = queryset.filter(license_no_lookup_hash=lookup_hash)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = create_organization_with_verification(
            owner=request.user,
            validated_data=dict(serializer.validated_data),
        )
        response_serializer = self.get_serializer(organization)
        headers = self.get_success_headers(response_serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

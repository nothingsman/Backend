from accounts.models import User
from analytics.models import InterventionLog
from analytics.services import build_student_analytics_payload
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from students.models import Student

from core.api.access import scope_intervention_queryset_for_user

from .serializers import InterventionLogSerializer
from .serializers import StudentAnalyticsResponseSerializer


class InterventionLogViewSet(viewsets.ModelViewSet):
    """
    CRUD for Intervention Logs.

    Records are auto-created by signals (e.g. low grade detection).
    Staff can update status (OPEN → IN_PROGRESS → RESOLVED) and add notes.

    Filters:
      ?organization=<id>
      ?student=<id>
      ?intervention_type=LOW_GRADE|ATTENDANCE|BEHAVIOUR|OTHER
      ?severity=LOW|MEDIUM|HIGH|CRITICAL
      ?status=OPEN|IN_PROGRESS|RESOLVED|DISMISSED

    Text search (?search=):
      Title, description
    """

    lookup_field = "id"
    permission_classes = [IsAuthenticated]
    serializer_class = InterventionLogSerializer
    filter_backends = [SearchFilter]
    search_fields = ["title", "description"]

    def get_queryset(self):
        qs = InterventionLog.objects.select_related("student", "organization")
        if getattr(self, "swagger_fake_view", False):
            return qs.none()

        qs = scope_intervention_queryset_for_user(qs, self.request.user)
        p = self.request.query_params
        if p.get("organization"):
            qs = qs.filter(organization_id=p["organization"])
        if p.get("student"):
            qs = qs.filter(student_id=p["student"])
        if p.get("intervention_type"):
            qs = qs.filter(intervention_type=p["intervention_type"].upper())
        if p.get("severity"):
            qs = qs.filter(severity=p["severity"].upper())
        if p.get("status"):
            qs = qs.filter(status=p["status"].upper())
        return qs

    def create(self, request, *args, **kwargs):
        self._enforce_teacher_write_restrictions()
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._enforce_teacher_write_restrictions()
        return super().destroy(request, *args, **kwargs)

    def _enforce_teacher_write_restrictions(self):
        role = getattr(self.request.user, "role", None)
        user_role = getattr(self.request.user, "Role", None)
        teacher_role = getattr(user_role, "TEACHER", None)
        if role == teacher_role:
            message = (
                "Teachers can update intervention logs but cannot create or delete "
                "them."
            )
            raise PermissionDenied(message)


@extend_schema(
    responses={200: StudentAnalyticsResponseSerializer},
)
class StudentAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, child_id):
        if request.user.role != User.Role.PARENT:
            message = "Only parents can access student analytics."
            raise PermissionDenied(message)

        try:
            parent_profile = request.user.parent_profile
        except ObjectDoesNotExist as exc:
            message = "Parent profile not found."
            raise PermissionDenied(message) from exc

        student = get_object_or_404(
            Student.objects.select_related(
                "current_section__academic_year",
                "current_section__grade",
                "organization",
                "branch",
            ).distinct(),
            id=child_id,
            parent_links__parent=parent_profile,
        )
        payload = {
            "success": True,
            "data": build_student_analytics_payload(student),
        }
        validator = StudentAnalyticsResponseSerializer(data=payload)
        validator.is_valid(raise_exception=True)
        response_serializer = StudentAnalyticsResponseSerializer(
            validator.validated_data,
        )
        return Response(response_serializer.data)

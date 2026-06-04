from academics.models import AcademicYear
from academics.models import Section
from academics.models import Subject
from accounts.models import User
from analytics.models import InterventionLog
from analytics.services import build_dashboard_overview_payload
from analytics.services import build_student_analytics_payload
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
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
from core.api.access import user_resource_access_filter

from .serializers import DashboardOverviewQuerySerializer
from .serializers import DashboardOverviewResponseSerializer
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
    parameters=[DashboardOverviewQuerySerializer],
    responses={200: DashboardOverviewResponseSerializer},
)
class DashboardOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = DashboardOverviewQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        validated = params.validated_data

        section = get_object_or_404(
            Section.objects.filter(
                self._section_access_filter(request.user),
            ).distinct(),
            id=validated["section_id"],
        )
        academic_year = get_object_or_404(
            AcademicYear.objects.filter(
                id=validated["academic_year_id"],
                organization=section.organization,
                branch=section.branch,
            ),
        )
        if section.academic_year_id != academic_year.id:
            return Response(
                {
                    "detail": (
                        "The provided academic_year_id does not match the section."
                    ),
                },
                status=400,
            )

        subject = None
        subject_id = validated.get("subject_id")
        if subject_id is not None:
            subject = get_object_or_404(
                Subject.objects.filter(
                    id=subject_id,
                    organization=section.organization,
                    branch=section.branch,
                    grade=section.grade,
                ),
            )

        payload = build_dashboard_overview_payload(
            section=section,
            academic_year=academic_year,
            subject=subject,
        )
        response_serializer = DashboardOverviewResponseSerializer(payload)
        return Response(response_serializer.data)

    def _section_access_filter(self, user) -> Q:
        return (
            user_resource_access_filter(
                user,
                organization_lookup="organization",
                branch_lookup="branch",
            )
            | Q(
                teacher_assignments__teacher__user=user,
            )
            | Q(
                homeroom_assignments__teacher__user=user,
            )
        )


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

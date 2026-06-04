import secrets

from accounts.email import ParentInvitationEmail
from accounts.models import User
from accounts.services import consume_parent_login_otp
from accounts.services import create_invitation_link
from accounts.services import create_parent_invitation_verification_token
from accounts.services import create_parent_login_otp
from accounts.sms import send_parent_invitation_sms
from accounts.sms import send_parent_otp_sms
from branches.models import Branch
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from student_insights.api.serializers import (
    ManualStudentInsightTriggerResponseSerializer,
)
from student_insights.services import trigger_manual_student_insight
from students.models import Parent
from students.models import ParentStudentLink
from students.models import Student
from students.models import StudentAcademicYearSection

from core.api.access import scope_parent_link_queryset_for_user
from core.api.access import scope_parent_queryset_for_user
from core.api.access import scope_student_queryset_for_user
from core.api.access import user_can_access_branch
from core.api.access import user_can_access_parent
from core.api.bulk_import import build_bulk_import_template_response
from core.models import ImportJob
from core.tasks import process_bulk_import

from .serializers import BulkImportSerializer
from .serializers import ParentCompleteInvitationSerializer
from .serializers import ParentInvitationOtpRequestSerializer
from .serializers import ParentInvitationOtpVerifySerializer
from .serializers import ParentInviteSerializer
from .serializers import ParentReadSerializer
from .serializers import ParentSerializer
from .serializers import ParentStudentLinkReadSerializer
from .serializers import ParentStudentLinkSerializer
from .serializers import StudentReadSerializer
from .serializers import StudentSerializer

STUDENT_LIST_PARAMETERS = [
    OpenApiParameter(
        name="section",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Filter by current section id.",
    ),
    OpenApiParameter(
        name="grade",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Filter by grade id.",
    ),
    OpenApiParameter(
        name="branch",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Filter by branch id.",
    ),
    OpenApiParameter(
        name="organization",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Filter by organization id.",
    ),
    OpenApiParameter(
        name="academic_year",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Filter by academic year id.",
    ),
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=[choice for choice, _label in Student.Status.choices],
        description="Filter by student status.",
    ),
    OpenApiParameter(
        name="gender",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=[choice for choice, _label in Student.Gender.choices],
        description="Filter by student gender.",
    ),
    OpenApiParameter(
        name="ordering",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Sort by field name. Prefix with '-' for descending. "
            "Allowed: roll_no, created_at, "
            "current_section__name, current_section__grade__name."
        ),
    ),
]

STUDENT_BY_SECTION_PARAMETERS = [
    OpenApiParameter(
        name="section",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Section id to list students from.",
        required=True,
    ),
    *[
        parameter
        for parameter in STUDENT_LIST_PARAMETERS
        if parameter.name not in {"section", "grade"}
    ],
]

STUDENT_BY_GRADE_PARAMETERS = [
    OpenApiParameter(
        name="grade",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Grade id to list students from.",
        required=True,
    ),
    *[
        parameter
        for parameter in STUDENT_LIST_PARAMETERS
        if parameter.name not in {"section", "grade"}
    ],
    OpenApiParameter(
        name="section",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Optional section id within the selected grade.",
    ),
]


def set_parent_activation_state(
    *,
    user: User,
    parent: Parent,
    is_active: bool,
    verified_at=None,
    update_password: bool = False,
) -> None:
    user.is_active = is_active
    user.verified_at = verified_at
    user_update_fields = ["is_active", "verified_at", "updated_at"]
    if update_password:
        user_update_fields.insert(0, "password")
    user.save(update_fields=user_update_fields)

    parent.is_active = is_active
    parent.save(update_fields=["is_active", "updated_at"])


PARENT_LIST_PARAMETERS = [
    OpenApiParameter(
        name="organization",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Filter by parent organization id.",
    ),
    OpenApiParameter(
        name="branch",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Filter by parent branch id.",
    ),
    OpenApiParameter(
        name="user",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Filter by linked user id.",
    ),
    OpenApiParameter(
        name="occupation",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="Filter by occupation.",
    ),
    OpenApiParameter(
        name="is_active",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        description="Filter by active parent profiles.",
    ),
]

PARENT_BY_BRANCH_PARAMETERS = [
    OpenApiParameter(
        name="branch",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Branch id to list parents from.",
        required=True,
    ),
]

PARENT_BY_ORGANIZATION_PARAMETERS = [
    OpenApiParameter(
        name="organization",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Organization id to list parents from.",
        required=True,
    ),
]

PARENT_LINK_LIST_PARAMETERS = [
    OpenApiParameter(
        name="student",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Filter by student id.",
    ),
    OpenApiParameter(
        name="parent",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        description="Filter by parent id.",
    ),
    OpenApiParameter(
        name="relationship_type",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=[choice for choice, _label in ParentStudentLink.Relationship.choices],
        description="Filter by relationship type.",
    ),
    OpenApiParameter(
        name="is_primary_contact",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        description="Filter by primary contact flag.",
    ),
]


@extend_schema_view(
    list=extend_schema(parameters=STUDENT_LIST_PARAMETERS),
    by_section=extend_schema(parameters=STUDENT_BY_SECTION_PARAMETERS),
    by_grade=extend_schema(parameters=STUDENT_BY_GRADE_PARAMETERS),
)
class StudentViewSet(viewsets.ModelViewSet):
    """
    CRUD for Students.

    Read responses automatically expand section, grade, branch, and
    academic-year details — no separate lookups needed.

    Query-param filters:
      ?section=<id>          Filter by current_section
      ?grade=<id>            Filter by section's grade
      ?branch=<id>           Filter by branch
      ?organization=<id>     Tenant filter
      ?academic_year=<id>    Filter by the academic year on the section
      ?status=ACTIVE|INACTIVE|WITHDRAWN|GRADUATED
      ?gender=MALE|FEMALE|OTHER

    Text search (?search=):
      Student roll number, section name, grade name

    Custom actions:
      GET /students/by-section/?section=<id>
          All students in a specific section with full details.

      GET /students/by-grade/?grade=<id>
          All students across every section of a grade with full details.
    """

    lookup_field = "id"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = [
        "roll_no",
        "current_section__name",
        "current_section__grade__name",
    ]
    ordering_fields = [
        "roll_no",
        "created_at",
        "current_section__name",
        "current_section__grade__name",
    ]
    ordering = ["created_at", "id"]

    def _base_queryset(self):
        return Student.objects.select_related(
            "current_section__grade",
            "current_section__academic_year",
            "branch",
            "organization",
            "photo",
        ).prefetch_related(
            Prefetch(
                "parent_links",
                queryset=ParentStudentLink.objects.select_related("parent__user"),
                to_attr="prefetched_parent_links",
            ),
        )

    def _apply_academic_year_filters(self, queryset, academic_year_id):
        filtered_assignment_qs = StudentAcademicYearSection.objects.filter(
            academic_year_id=academic_year_id,
        ).select_related(
            "academic_year",
            "section__grade",
        )
        queryset = queryset.prefetch_related(
            Prefetch(
                "academic_year_sections",
                queryset=filtered_assignment_qs,
                to_attr="filtered_academic_year_sections",
            ),
        ).filter(
            academic_year_sections__academic_year_id=academic_year_id,
        )

        params = self.request.query_params
        if params.get("section"):
            queryset = queryset.filter(
                academic_year_sections__section_id=params["section"],
            )
        if params.get("grade"):
            queryset = queryset.filter(
                academic_year_sections__section__grade_id=params["grade"],
            )

        return queryset

    def _apply_current_section_filters(self, queryset):
        params = self.request.query_params
        if params.get("section"):
            queryset = queryset.filter(current_section_id=params["section"])
        if params.get("grade"):
            queryset = queryset.filter(current_section__grade_id=params["grade"])
        return queryset

    def get_queryset(self):
        params = self.request.query_params
        qs = self._base_queryset()
        if getattr(self, "swagger_fake_view", False):
            return qs.none()

        academic_year_id = params.get("academic_year")
        qs = scope_student_queryset_for_user(
            qs,
            self.request.user,
            academic_year_id=academic_year_id,
        )
        if academic_year_id:
            qs = self._apply_academic_year_filters(qs, academic_year_id)
        else:
            qs = self._apply_current_section_filters(qs)
        if params.get("branch"):
            qs = qs.filter(branch_id=params["branch"])
        if params.get("organization"):
            qs = qs.filter(organization_id=params["organization"])
        if params.get("status"):
            qs = qs.filter(status=params["status"].upper())
        if params.get("gender"):
            qs = qs.filter(gender=params["gender"].upper())
        return qs.distinct()

    def get_serializer_class(self):
        if self.action == "bulk_import":
            return BulkImportSerializer
        if self.action in ["list", "retrieve", "by_section", "by_grade"]:
            return StudentReadSerializer
        return StudentSerializer

    # ------------------------------------------------------------------
    # POST /students/bulk-import/
    # ------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="bulk-import")
    def bulk_import(self, request):
        """Bulk import students from CSV/Excel."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization_id = serializer.validated_data["organization"]
        branch_id = serializer.validated_data["branch"]
        media_file = serializer.validated_data["file"]
        current_section = serializer.validated_data.get("current_section")

        # Permission check
        try:
            branch = Branch.objects.select_related("organization").get(
                id=branch_id,
                organization_id=organization_id,
            )
        except Branch.DoesNotExist:
            return Response(
                {"detail": "Branch not found or does not belong to organization."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user_can_access_branch(request.user, branch):
            return Response(
                {"detail": "You do not have permission to import to this branch."},
                status=status.HTTP_403_FORBIDDEN,
            )

        import_job = ImportJob.objects.create(
            file=media_file,
            module="students",
            organization_id=organization_id,
            branch_id=branch_id,
            current_section=current_section,
            created_by=request.user,
        )

        process_bulk_import.delay(str(import_job.id))

        return Response(
            {"task_id": str(import_job.id), "detail": "Bulk import process started."},
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(
        summary="Download Student Bulk Import Template",
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=["get"], url_path="bulk-import-template")
    def bulk_import_template(self, request):
        return build_bulk_import_template_response(
            template_name="bulk_import/students_bulk_import_template.csv",
            filename="students_bulk_import_template.csv",
        )

    # ------------------------------------------------------------------
    # GET /students/by-section/?section=<id>[&status=][&academic_year=]
    # ------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="by-section")
    @extend_schema(
        parameters=STUDENT_BY_SECTION_PARAMETERS,
    )
    def by_section(self, request):
        """
        Return all students in the given section with full details.
        Required: ?section=<uuid>
        Optional: ?status=ACTIVE, ?academic_year=<uuid>
        """
        section_id = request.query_params.get("section")
        if not section_id:
            return Response(
                {"detail": "Query parameter 'section' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = self.get_queryset()
        if request.query_params.get("academic_year"):
            qs = qs.filter(academic_year_sections__section_id=section_id)
        else:
            qs = qs.filter(current_section_id=section_id)
        qs = self.filter_queryset(qs)
        serializer = StudentReadSerializer(
            qs,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    @extend_schema(
        summary="Manually trigger a student insight",
        responses={200: ManualStudentInsightTriggerResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="trigger-insight")
    def trigger_insight(self, request, **kwargs):
        del kwargs
        if request.user.role != User.Role.TEACHER:
            return Response(
                {"detail": "Only teachers can trigger student insights."},
                status=status.HTTP_403_FORBIDDEN,
            )

        student = self.get_object()
        result = trigger_manual_student_insight(
            student_id=str(student.id),
            triggered_by_user=request.user,
        )
        payload = {
            "created": result.created,
            "reused_existing": result.reused_existing,
            "message": result.message,
            "reason_code": result.reason_code,
            "source_event_type": result.source_event_type,
            "source_model": result.source_model,
            "source_id": result.source_id,
        }
        if result.insight is not None:
            payload.update(
                {
                    "insight_id": str(result.insight.id),
                    "category": result.insight.category,
                    "risk_band": result.insight.risk_band,
                    "delivery_status": result.insight.delivery_status,
                },
            )

        serializer = ManualStudentInsightTriggerResponseSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # GET /students/by-grade/?grade=<id>[&status=][&section=]
    # ------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="by-grade")
    @extend_schema(
        parameters=STUDENT_BY_GRADE_PARAMETERS,
    )
    def by_grade(self, request):
        """
        Return all students across all sections of a given grade.
        Required: ?grade=<uuid>
        Optional: ?section=<uuid>, ?status=ACTIVE, ?academic_year=<uuid>
        """
        grade_id = request.query_params.get("grade")
        if not grade_id:
            return Response(
                {"detail": "Query parameter 'grade' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = self.get_queryset()
        if request.query_params.get("academic_year"):
            qs = qs.filter(academic_year_sections__section__grade_id=grade_id)
        else:
            qs = qs.filter(current_section__grade_id=grade_id)
        qs = self.filter_queryset(qs)
        serializer = StudentReadSerializer(
            qs,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(parameters=PARENT_LIST_PARAMETERS),
    by_branch=extend_schema(parameters=PARENT_BY_BRANCH_PARAMETERS),
    by_organization=extend_schema(parameters=PARENT_BY_ORGANIZATION_PARAMETERS),
)
class ParentViewSet(viewsets.ModelViewSet):
    """CRUD for parent profiles and related branch/organization lookups."""

    lookup_field = "id"
    permission_classes = [IsAuthenticated]
    filter_backends = []

    def get_queryset(self):
        qs = Parent.objects.all()
        if getattr(self, "swagger_fake_view", False):
            return qs.none()

        qs = scope_parent_queryset_for_user(qs, self.request.user)
        params = self.request.query_params
        if params.get("organization"):
            qs = qs.filter(organizations__id=params["organization"])
        if params.get("branch"):
            qs = qs.filter(branches__id=params["branch"])
        if params.get("user"):
            qs = qs.filter(user_id=params["user"])
        if params.get("occupation"):
            normalized_occupation = params["occupation"].strip().casefold()
            matching_ids = [
                parent.id
                for parent in qs.only("id", "occupation")
                if parent.occupation.strip().casefold() == normalized_occupation
            ]
            qs = qs.filter(id__in=matching_ids)
        if params.get("is_active") is not None:
            is_active = params["is_active"].lower() in ("true", "1", "yes")
            qs = qs.filter(is_active=is_active)
        return (
            qs.select_related("user")
            .prefetch_related(
                "organizations",
                "branches",
                "student_links__student",
            )
            .distinct()
        )

    def get_serializer_class(self):
        if self.action == "bulk_import":
            return BulkImportSerializer
        if self.action in [
            "list",
            "retrieve",
            "by_branch",
            "by_organization",
            "branches",
            "organizations",
            "students",
            "me",
            "my_students",
        ]:
            return ParentReadSerializer
        return ParentSerializer

    # ------------------------------------------------------------------
    # POST /parents/bulk-import/
    # ------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="bulk-import")
    def bulk_import(self, request):
        """Bulk import parents from CSV/Excel."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization_id = serializer.validated_data["organization"]
        branch_id = serializer.validated_data["branch"]
        media_file = serializer.validated_data["file"]

        # Permission check
        try:
            branch = Branch.objects.select_related("organization").get(
                id=branch_id,
                organization_id=organization_id,
            )
        except Branch.DoesNotExist:
            return Response(
                {"detail": "Branch not found or does not belong to organization."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user_can_access_branch(request.user, branch):
            return Response(
                {"detail": "You do not have permission to import to this branch."},
                status=status.HTTP_403_FORBIDDEN,
            )

        import_job = ImportJob.objects.create(
            file=media_file,
            module="parents",
            organization_id=organization_id,
            branch_id=branch_id,
            created_by=request.user,
        )

        process_bulk_import.delay(str(import_job.id))

        return Response(
            {"task_id": str(import_job.id), "detail": "Bulk import process started."},
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(
        summary="Download Parent Bulk Import Template",
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=["get"], url_path="bulk-import-template")
    def bulk_import_template(self, request):
        return build_bulk_import_template_response(
            template_name="bulk_import/parents_bulk_import_template.csv",
            filename="parents_bulk_import_template.csv",
        )

    @action(detail=False, methods=["get"], url_path="by-branch")
    @extend_schema(parameters=PARENT_BY_BRANCH_PARAMETERS)
    def by_branch(self, request):
        branch_id = request.query_params.get("branch")
        if not branch_id:
            return Response(
                {"detail": "Query parameter 'branch' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = self.filter_queryset(self.get_queryset().filter(branches__id=branch_id))
        serializer = ParentReadSerializer(
            qs,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="by-organization")
    @extend_schema(parameters=PARENT_BY_ORGANIZATION_PARAMETERS)
    def by_organization(self, request):
        organization_id = request.query_params.get("organization")
        if not organization_id:
            return Response(
                {"detail": "Query parameter 'organization' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = self.filter_queryset(
            self.get_queryset().filter(organizations__id=organization_id),
        )
        serializer = ParentReadSerializer(
            qs,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="branches")
    def branches(self, request, **kwargs):
        parent = self.get_object()
        return Response(
            ParentReadSerializer(parent, context={"request": request}).data[
                "branch_details"
            ],
        )

    @action(detail=True, methods=["get"], url_path="organizations")
    def organizations(self, request, **kwargs):
        parent = self.get_object()
        return Response(
            ParentReadSerializer(parent, context={"request": request}).data[
                "organization_details"
            ],
        )

    @action(detail=True, methods=["get"], url_path="students")
    def students(self, request, **kwargs):
        parent = self.get_object()
        return Response(
            ParentReadSerializer(parent, context={"request": request}).data[
                "student_details"
            ],
        )

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        try:
            parent = request.user.parent_profile
        except Parent.DoesNotExist:
            return Response(
                {"detail": "No parent profile found for the authenticated user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not user_can_access_parent(request.user, parent):
            return Response(
                {"detail": "You do not have access to this parent profile."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            ParentReadSerializer(parent, context={"request": request}).data,
        )

    @action(detail=False, methods=["get"], url_path="my-students")
    def my_students(self, request):
        try:
            parent = request.user.parent_profile
        except Parent.DoesNotExist:
            return Response(
                {"detail": "No parent profile found for the authenticated user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        students = [
            link.student
            for link in parent.student_links.select_related(
                "student__current_section__grade",
                "student__current_section__academic_year",
                "student__branch",
                "student__organization",
            )
        ]
        return Response(StudentReadSerializer(students, many=True).data)


@extend_schema_view(
    list=extend_schema(parameters=PARENT_LINK_LIST_PARAMETERS),
)
class ParentStudentLinkViewSet(viewsets.ModelViewSet):
    """
    CRUD for parent-student relationships.
    Read responses include full student and parent details.
    """

    queryset = (
        ParentStudentLink.objects.select_related(
            "student__current_section__grade",
            "student__current_section__academic_year",
            "student__branch",
            "parent__user",
        )
        .prefetch_related(
            "parent__organizations",
            "parent__branches",
        )
        .all()
    )
    lookup_field = "id"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()

        qs = scope_parent_link_queryset_for_user(self.queryset, self.request.user)
        params = self.request.query_params
        if params.get("student"):
            qs = qs.filter(student_id=params["student"])
        if params.get("parent"):
            qs = qs.filter(parent_id=params["parent"])
        if params.get("relationship_type"):
            qs = qs.filter(
                relationship_type=params["relationship_type"].upper(),
            )
        if params.get("is_primary_contact") is not None:
            is_primary_contact = params["is_primary_contact"].lower() in (
                "true",
                "1",
                "yes",
            )
            qs = qs.filter(is_primary_contact=is_primary_contact)

        return qs.distinct()

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return ParentStudentLinkReadSerializer
        return ParentStudentLinkSerializer


@extend_schema(request=ParentInviteSerializer)
class ParentInviteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ParentInviteSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        branch: Branch = data["branch"]

        with transaction.atomic():
            sms_sent = False
            sms_error = ""
            random_password = secrets.token_urlsafe(16)
            existing_user = data.get("existing_user")
            if existing_user is None:
                user = User.objects.create_user(
                    email=data.get("email") or None,
                    password=random_password,
                    name=data["name"],
                    father_name=data["father_name"],
                    grandfather_name=data["grandfather_name"],
                    phone_number=data["phone_number"],
                    role=User.Role.PARENT,
                    is_active=False,
                )
                parent = Parent.objects.create(
                    user=user,
                    secondary_phone_number=data.get("secondary_phone_number", ""),
                    occupation=data.get("occupation", ""),
                    work_address=data.get("work_address", ""),
                    relationship_notes=data.get("relationship_notes", ""),
                    emergency_contact_name=data.get("emergency_contact_name", ""),
                    emergency_contact_phone=data.get("emergency_contact_phone", ""),
                    is_active=False,
                )
            else:
                user = existing_user
                user.name = data["name"]
                user.father_name = data["father_name"]
                user.grandfather_name = data["grandfather_name"]
                user.phone_number = data["phone_number"]
                user.email = data.get("email") or None
                user.role = User.Role.PARENT
                user.is_active = False
                user.verified_at = None
                user.set_password(random_password)
                user.save(
                    update_fields=[
                        "name",
                        "father_name",
                        "grandfather_name",
                        "phone_number",
                        "email",
                        "role",
                        "is_active",
                        "verified_at",
                        "password",
                    ],
                )

                parent = user.parent_profile
                parent.secondary_phone_number = data.get("secondary_phone_number", "")
                parent.occupation = data.get("occupation", "")
                parent.work_address = data.get("work_address", "")
                parent.relationship_notes = data.get("relationship_notes", "")
                parent.emergency_contact_name = data.get("emergency_contact_name", "")
                parent.emergency_contact_phone = data.get(
                    "emergency_contact_phone",
                    "",
                )
                parent.is_active = False
                parent.save(
                    update_fields=[
                        "secondary_phone_number",
                        "occupation",
                        "work_address",
                        "relationship_notes",
                        "emergency_contact_name",
                        "emergency_contact_phone",
                        "is_active",
                        "updated_at",
                    ],
                )
                parent.organizations.clear()
                parent.branches.clear()

            parent.organizations.add(branch.organization)
            parent.branches.add(branch)

            # Ensure invited parents always remain inactive until invitation completion.
            set_parent_activation_state(
                user=user,
                parent=parent,
                is_active=False,
                verified_at=None,
            )

            invitation_link = create_invitation_link(
                user=user,
                path_template="complete-parent-invitation/{uid}/{token}",
            )
            try:
                send_parent_invitation_sms(
                    phone_number=user.phone_number or "",
                    invitation_url=invitation_link.full_url,
                )
                sms_sent = True
            except (RuntimeError, ValueError, TypeError) as exc:
                sms_error = str(exc)
            email_obj = ParentInvitationEmail(
                request,
                context={
                    "user": user,
                    "branch_name": branch.name,
                    "invited_by": request.user.name,
                    "url": invitation_link.path,
                },
            )
            if user.email:
                email_obj.send([user.email])

            response_data = {
                "message": "Parent invitation sent successfully.",
                "invitation_url": invitation_link.full_url,
                "sms_sent": sms_sent,
            }
            if sms_error:
                response_data["sms_error"] = sms_error

            return Response(
                response_data,
                status=status.HTTP_201_CREATED,
            )


@extend_schema(request=ParentInvitationOtpRequestSerializer)
class ParentInvitationOtpRequestView(APIView):
    permission_classes = []

    def post(self, request):
        serializer = ParentInvitationOtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.context["target_user"]

        with transaction.atomic():
            otp_code = create_parent_login_otp(user=user)
            send_parent_otp_sms(
                phone_number=user.phone_number or "",
                otp_code=otp_code,
            )

        return Response(
            {"message": "OTP sent successfully."},
            status=status.HTTP_200_OK,
        )


@extend_schema(request=ParentInvitationOtpVerifySerializer)
class ParentInvitationOtpVerifyView(APIView):
    permission_classes = []

    def post(self, request):
        serializer = ParentInvitationOtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.context["target_user"]
        consume_parent_login_otp(
            user=user,
            raw_code=serializer.validated_data["otp_code"],
        )
        verification_token = create_parent_invitation_verification_token(user=user)

        return Response(
            {
                "message": "OTP verified successfully.",
                "invitation_verification_token": verification_token,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(request=ParentCompleteInvitationSerializer)
class ParentCompleteInvitationView(APIView):
    permission_classes = []

    def post(self, request):
        serializer = ParentCompleteInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.context["target_user"]
        parent_profile = serializer.context["target_parent_profile"]

        user.set_password(serializer.validated_data["new_password"])
        set_parent_activation_state(
            user=user,
            parent=parent_profile,
            is_active=True,
            verified_at=timezone.now(),
            update_password=True,
        )

        return Response(
            {"message": "Password set and parent account activated successfully."},
            status=status.HTTP_200_OK,
        )

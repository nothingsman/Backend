from assessments.models import Assessment
from assessments.models import AssessmentResult
from assessments.models import HomeworkConfirmation
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.api.access import scope_assessment_result_queryset_for_user
from core.api.access import teacher_section_access_filter
from core.api.access import user_can_access_student_as_parent_or_staff
from core.api.access import user_can_manage_branch
from core.api.access import user_resource_access_filter

from .serializers import AssessmentReadSerializer
from .serializers import AssessmentResultReadSerializer
from .serializers import AssessmentResultSerializer
from .serializers import AssessmentSerializer
from .serializers import BulkGradeSerializer
from .serializers import HomeworkConfirmationSerializer
from .serializers import ParentHomeworkConfirmSerializer
from .serializers import TodaysHomeworkReadSerializer

# ---------------------------------------------------------------------------
# Assessment ViewSet
# ---------------------------------------------------------------------------


def scope_assessment_queryset_for_user(queryset, user):
    access_filter = user_resource_access_filter(user)
    if getattr(user, "is_authenticated", False):
        access_filter |= Q(teacher_assignment__teacher__user=user)
    return queryset.filter(access_filter).distinct()


def _is_truthy_query_value(value):
    return value is not None and value.lower() in ("true", "1", "yes")


class AssessmentViewSet(viewsets.ModelViewSet):
    """
    CRUD for Assessments (Assignments, Exams, Homework, Quizzes, etc.).

    Query-param filters:
      ?organization=<id>
      ?branch=<id>
      ?teacher_assignment=<id>
      ?teacher=<id>
      ?section=<id>
      ?subject=<id>
      ?task_type=ASSIGNMENT|EXAM|QUIZ|HOMEWORK|PROJECT|LAB
      ?status=DRAFT|PUBLISHED|CLOSED

    Text search (?search=):
      Title, description, section name, subject name.

    Custom actions:
      GET  /assessments/by-section/?section=<id>
           All assessments for a given section (all subjects).

      GET  /assessments/by-teacher/?teacher=<id>
           All assessments created under a teacher's assignments.
    """

    lookup_field = "id"
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter]
    search_fields = [
        "title",
        "description",
        "teacher_assignment__section__name",
        "teacher_assignment__subject__name",
    ]

    def get_queryset(self):
        qs = Assessment.objects.select_related(
            "teacher_assignment__section__grade",
            "teacher_assignment__subject",
            "teacher_assignment__teacher__user",
            "teacher_assignment__academic_year",
            "branch",
            "organization",
        )
        if getattr(self, "swagger_fake_view", False):
            return qs.none()

        qs = scope_assessment_queryset_for_user(qs, self.request.user)
        return self._apply_assessment_filters(qs)

    def get_serializer_class(self):
        if self.action in [
            "list",
            "retrieve",
            "by_section",
            "by_teacher",
            "todays_homework",
        ]:
            return AssessmentReadSerializer
        return AssessmentSerializer

    def _apply_assessment_filters(self, queryset):
        filters = {
            "organization": "organization_id",
            "branch": "branch_id",
            "teacher_assignment": "teacher_assignment_id",
            "teacher": "teacher_assignment__teacher_id",
            "section": "teacher_assignment__section_id",
            "subject": "teacher_assignment__subject_id",
        }
        queryset_filters = {}
        for param, lookup in filters.items():
            value = self.request.query_params.get(param)
            if value:
                queryset_filters[lookup] = value

        if queryset_filters:
            queryset = queryset.filter(**queryset_filters)

        task_type = self.request.query_params.get("task_type")
        if task_type:
            queryset = queryset.filter(task_type=task_type.upper())

        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value.upper())

        return queryset

    def _get_homework_base_queryset(self):
        queryset = self.get_queryset().filter(
            task_type=Assessment.TaskType.HOMEWORK,
            due_date=timezone.localdate(),
            status=Assessment.Status.PUBLISHED,
        )
        branch_id = self.request.query_params.get("branch")
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)

        section_id = self.request.query_params.get("section")
        if section_id:
            queryset = queryset.filter(teacher_assignment__section_id=section_id)

        return queryset

    def _get_parent_profile(self):
        try:
            return self.request.user.parent_profile
        except ObjectDoesNotExist:
            return None

    def _get_student_queryset(self, parent_profile, student_id):
        student_model = __import__("students.models", fromlist=["Student"]).Student
        students = student_model.objects.select_related("current_section")
        if parent_profile is not None:
            return students.filter(parent_links__parent=parent_profile).distinct()
        if student_id:
            return students.filter(id=student_id)
        return None

    def _build_confirmation_maps(self, queryset, students):
        confirmations = HomeworkConfirmation.objects.filter(
            assessment_id__in=queryset.values_list("id", flat=True),
        )
        if students is not None:
            confirmations = confirmations.filter(
                student_id__in=students.values_list("id", flat=True),
            )
        confirmations = confirmations.select_related("assessment", "student")

        confirmation_map = {
            (confirmation.assessment_id, confirmation.student_id): confirmation
            for confirmation in confirmations
        }
        assessment_confirmation_map = {}
        for confirmation in confirmations:
            assessment_confirmation_map.setdefault(
                confirmation.assessment_id,
                [],
            ).append(confirmation)

        return confirmation_map, assessment_confirmation_map

    def _matches_confirmed_filter(self, confirmed):
        confirmed_filter = self.request.query_params.get("confirmed")
        if confirmed_filter is None:
            return True
        return confirmed == _is_truthy_query_value(confirmed_filter)

    def _build_student_homework_rows(
        self,
        assessment,
        students,
        confirmation_map,
    ):
        rows = []
        matching_students = students.filter(
            current_section_id=assessment.teacher_assignment.section_id,
            branch_id=assessment.branch_id,
            organization_id=assessment.organization_id,
        )
        for student in matching_students:
            confirmation = confirmation_map.get((assessment.id, student.id))
            confirmed = bool(confirmation and confirmation.is_confirmed)
            if not self._matches_confirmed_filter(confirmed):
                continue
            rows.append(
                {
                    "assessment": assessment,
                    "student": student,
                    "confirmed": confirmed,
                    "homework_confirmation": confirmation,
                },
            )
        return rows

    def _build_assessment_homework_row(self, assessment, assessment_confirmation_map):
        assessment_confirmations = assessment_confirmation_map.get(assessment.id, [])
        assessment_confirmed = any(
            confirmation.is_confirmed for confirmation in assessment_confirmations
        )
        if not self._matches_confirmed_filter(assessment_confirmed):
            return None

        return {
            "assessment": assessment,
            "student": None,
            "confirmed": assessment_confirmed,
            "homework_confirmation": assessment_confirmations[0]
            if assessment_confirmations
            else None,
        }

    def _build_todays_homework_rows(self):
        qs = self._get_homework_base_queryset()
        student_id = self.request.query_params.get("student")
        parent_profile = self._get_parent_profile()
        students = self._get_student_queryset(parent_profile, student_id)
        include_student_rows = parent_profile is not None or bool(student_id)

        if students is not None and student_id:
            students = students.filter(id=student_id)

        confirmation_map, assessment_confirmation_map = self._build_confirmation_maps(
            qs,
            students,
        )

        rows = []
        for assessment in qs:
            if include_student_rows:
                rows.extend(
                    self._build_student_homework_rows(
                        assessment,
                        students,
                        confirmation_map,
                    ),
                )
                continue

            row = self._build_assessment_homework_row(
                assessment,
                assessment_confirmation_map,
            )
            if row is not None:
                rows.append(row)
        return rows

    # ------------------------------------------------------------------
    # GET /assessments/by-section/?section=<id>[&task_type=][&status=]
    # ------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="by-section")
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="section",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter by section ID.",
                required=True,
            ),
        ],
    )
    def by_section(self, request):
        """All assessments for a given section across all subjects."""
        section_id = request.query_params.get("section")
        if not section_id:
            return Response(
                {"detail": "Query parameter 'section' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = self.get_queryset().filter(teacher_assignment__section_id=section_id)
        qs = self.filter_queryset(qs)
        serializer = AssessmentReadSerializer(qs, many=True)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # GET /assessments/by-teacher/?teacher=<id>[&task_type=][&status=]
    # ------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="by-teacher")
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="teacher",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter by teacher ID.",
                required=True,
            ),
        ],
    )
    def by_teacher(self, request):
        """All assessments created by/for a specific teacher."""
        teacher_id = request.query_params.get("teacher")
        if not teacher_id:
            return Response(
                {"detail": "Query parameter 'teacher' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = self.get_queryset().filter(teacher_assignment__teacher_id=teacher_id)
        qs = self.filter_queryset(qs)
        serializer = AssessmentReadSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="todays-homework")
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="student",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter by student ID.",
                required=False,
            ),
            OpenApiParameter(
                name="section",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter by section ID.",
                required=False,
            ),
            OpenApiParameter(
                name="branch",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter by branch ID.",
                required=False,
            ),
            OpenApiParameter(
                name="confirmed",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Filter by homework confirmation state.",
                required=False,
            ),
        ],
    )
    def todays_homework(self, request):
        rows = self._build_todays_homework_rows()
        page = self.paginate_queryset(rows)
        if page is not None:
            serializer = TodaysHomeworkReadSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = TodaysHomeworkReadSerializer(rows, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# AssessmentResult ViewSet
# ---------------------------------------------------------------------------


class AssessmentResultViewSet(viewsets.ModelViewSet):
    """
    CRUD for individual Assessment Results.

    Query-param filters:
      ?organization=<id>
      ?assessment=<id>
      ?student=<id>
      ?submission_status=PENDING|SUBMITTED|LATE|MISSING|GRADED
      ?parent_confirmed=true|false

    Text search (?search=):
      Student first/last name, roll number, assessment title.

    Custom actions:
      POST /assessment-results/bulk-grade/
           Teacher submits grades for a whole section in one request.

      PATCH /assessment-results/<id>/confirm-homework/
           Parent confirms their child completed the homework.

      GET  /assessment-results/by-assessment/?assessment=<id>
           All results for one assessment (full section overview).

      GET  /assessment-results/by-student/?student=<id>
           All results for one student across all assessments.
    """

    lookup_field = "id"
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter]
    search_fields = [
        "student__roll_no",
        "assessment__title",
    ]

    def get_queryset(self):
        qs = AssessmentResult.objects.select_related(
            "assessment__teacher_assignment__section__grade",
            "assessment__teacher_assignment__subject",
            "assessment__teacher_assignment__teacher__user",
            "assessment__teacher_assignment__academic_year",
            "student",
            "graded_by",
            "organization",
            "assessment__branch",
        )
        if getattr(self, "swagger_fake_view", False):
            return qs.none()

        if self.action == "confirm_homework":
            qs = qs.filter(
                user_resource_access_filter(
                    self.request.user,
                    branch_lookup="assessment__branch",
                )
                | Q(student__parent_links__parent__user=self.request.user),
            ).distinct()
        elif self.action == "todays_homework":
            qs = self._scope_todays_homework_queryset(qs)
        else:
            qs = scope_assessment_result_queryset_for_user(qs, self.request.user)
        return self._apply_result_filters(qs)

    def get_serializer_class(self):
        if self.action in [
            "list",
            "retrieve",
            "by_assessment",
            "by_student",
            "todays_homework",
        ]:
            return AssessmentResultReadSerializer
        if self.action == "confirm_homework":
            return ParentHomeworkConfirmSerializer
        return AssessmentResultSerializer

    def _scope_todays_homework_queryset(self, queryset):
        access_filter = Q(pk__in=[])
        if getattr(self.request.user, "is_authenticated", False):
            try:
                parent_profile = self.request.user.parent_profile
                is_parent = True
            except ObjectDoesNotExist:
                parent_profile = None
                is_parent = False
            if is_parent:
                access_filter |= Q(
                    student__parent_links__parent=parent_profile,
                )
            else:
                access_filter |= user_resource_access_filter(
                    self.request.user,
                    branch_lookup="assessment__branch",
                )
            access_filter |= Q(
                assessment__teacher_assignment__teacher__user=self.request.user,
            )
            access_filter |= teacher_section_access_filter(
                self.request.user,
                section_lookup="assessment__teacher_assignment__section",
            )
        return queryset.filter(access_filter).distinct()

    def _apply_result_filters(self, queryset):
        filters = {
            "organization": "organization_id",
            "assessment": "assessment_id",
            "student": "student_id",
            "section": "assessment__teacher_assignment__section_id",
            "branch": "assessment__branch_id",
        }
        queryset_filters = {}
        for param, lookup in filters.items():
            value = self.request.query_params.get(param)
            if value:
                queryset_filters[lookup] = value

        if queryset_filters:
            queryset = queryset.filter(**queryset_filters)

        submission_status = self.request.query_params.get("submission_status")
        if submission_status:
            queryset = queryset.filter(submission_status=submission_status.upper())

        for param in ("parent_confirmed", "confirmed"):
            value = self.request.query_params.get(param)
            if value is not None:
                queryset = queryset.filter(
                    parent_confirmed=_is_truthy_query_value(value),
                )

        return queryset

    def perform_create(self, serializer):
        self._enforce_teacher_result_access(
            serializer.validated_data["assessment"],
        )
        serializer.save(graded_by=self.request.user)

    def perform_update(self, serializer):
        assessment = serializer.validated_data.get(
            "assessment",
            serializer.instance.assessment,
        )
        self._enforce_teacher_result_access(assessment)
        serializer.save(graded_by=self.request.user)

    def _enforce_teacher_result_access(self, assessment):
        if user_can_manage_branch(self.request.user, assessment.branch):
            return

        if assessment.teacher_assignment.teacher.user_id == self.request.user.id:
            return

        message = "You do not have permission to manage results for this assessment."
        raise PermissionDenied(message)

    # ------------------------------------------------------------------
    # POST /assessment-results/bulk-grade/
    # ------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="bulk-grade")
    def bulk_grade(self, request):
        """
        Teacher posts grades for a whole section at once.

        Payload:
        {
          "assessment": "<uuid>",
          "results": [
            {"student": "<uuid>", "obtained_marks": 38, "submission_status": "GRADED"},
            {"student": "<uuid>", "submission_status": "MISSING"},
            ...
          ]
        }

        Idempotent: existing result rows are updated; new ones are created.
        The post_save signal fires for each saved result, triggering the
        low-grade intervention check in the analytics app.
        """
        serializer = BulkGradeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assessment = serializer.validated_data["assessment"]
        items = serializer.validated_data["results"]

        self._enforce_teacher_result_access(assessment)

        created_ids, updated_ids, errors = [], [], []

        with transaction.atomic():
            for item in items:
                try:
                    obj, was_created = AssessmentResult.objects.update_or_create(
                        assessment=assessment,
                        student=item["student"],
                        defaults={
                            "organization": assessment.organization,
                            "graded_by": request.user,
                            "obtained_marks": item.get("obtained_marks"),
                            "submission_status": item["submission_status"],
                            "feedback": item.get("feedback", ""),
                        },
                    )
                    if was_created:
                        created_ids.append(str(obj.id))
                    else:
                        updated_ids.append(str(obj.id))
                except IntegrityError as exc:
                    errors.append(
                        {"student": str(item["student"].id), "error": str(exc)},
                    )

        return Response(
            {
                "assessment": str(assessment.id),
                "created": len(created_ids),
                "updated": len(updated_ids),
                "errors": errors,
            },
            status=status.HTTP_207_MULTI_STATUS if errors else status.HTTP_200_OK,
        )

    # ------------------------------------------------------------------
    # PATCH /assessment-results/<id>/confirm-homework/
    # ------------------------------------------------------------------
    @action(detail=True, methods=["patch"], url_path="confirm-homework")
    def confirm_homework(self, request, pk=None):
        """
        Parent endpoint to confirm their child completed a homework task.

        Validates that:
          - The assessment is of type HOMEWORK.
          - The confirmation hasn't already been set.

        TODO: Add a permission class to restrict this to the student's
              linked parents (check students.ParentStudentLink).
        """
        result = self.get_object()
        if not user_can_access_student_as_parent_or_staff(request.user, result.student):
            message = "You cannot confirm this homework result."
            raise PermissionDenied(message)

        serializer = ParentHomeworkConfirmSerializer(
            result,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        data = {
            "assessment": result.assessment_id,
            "student": result.student_id,
            "is_confirmed": serializer.validated_data.get("parent_confirmed", True),
            "feedback": serializer.validated_data.get("feedback", ""),
        }
        confirmation_serializer = HomeworkConfirmationSerializer(
            data=data,
            context={"request": request},
        )
        confirmation_serializer.is_valid(raise_exception=True)
        confirmation_serializer.save()
        return Response(
            AssessmentResultReadSerializer(
                result,
                context={"request": request},
            ).data,
        )

    @action(detail=False, methods=["get"], url_path="todays-homework")
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="student",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter by student ID.",
                required=False,
            ),
            OpenApiParameter(
                name="section",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter by section ID.",
                required=False,
            ),
            OpenApiParameter(
                name="branch",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter by branch ID.",
                required=False,
            ),
            OpenApiParameter(
                name="confirmed",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Filter by homework confirmation state.",
                required=False,
            ),
        ],
    )
    def todays_homework(self, request):
        today = timezone.localdate()
        qs = self.get_queryset().filter(
            assessment__task_type=Assessment.TaskType.HOMEWORK,
            assessment__due_date=today,
        )
        qs = self.filter_queryset(qs)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = AssessmentResultReadSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = AssessmentResultReadSerializer(qs, many=True)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # GET /assessment-results/by-assessment/?assessment=<id>
    # ------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="by-assessment")
    def by_assessment(self, request):
        """
        Full result list for one assessment — gives the teacher a
        section-level grade overview.
        """
        assessment_id = request.query_params.get("assessment")
        if not assessment_id:
            return Response(
                {"detail": "Query parameter 'assessment' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = self.get_queryset().filter(assessment_id=assessment_id)
        qs = self.filter_queryset(qs)
        serializer = AssessmentResultReadSerializer(qs, many=True)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # GET /assessment-results/by-student/?student=<id>
    # ------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="by-student")
    def by_student(self, request):
        """
        Full assessment history for one student — useful for parent / student
        portal views.
        Optional: ?assessment__task_type=HOMEWORK to filter by type.
        """
        student_id = request.query_params.get("student")
        if not student_id:
            return Response(
                {"detail": "Query parameter 'student' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = self.get_queryset().filter(student_id=student_id)
        task_type = request.query_params.get("task_type")
        if task_type:
            qs = qs.filter(assessment__task_type=task_type.upper())
        qs = self.filter_queryset(qs)
        serializer = AssessmentResultReadSerializer(qs, many=True)
        return Response(serializer.data)


class HomeworkConfirmationViewSet(viewsets.GenericViewSet):
    queryset = HomeworkConfirmation.objects.select_related(
        "organization",
        "branch",
        "section",
        "assessment",
        "student",
        "confirmed_by",
    )
    serializer_class = HomeworkConfirmationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["post"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        student = serializer.validated_data["student"]
        if not user_can_access_student_as_parent_or_staff(request.user, student):
            message = "You cannot confirm this homework result."
            raise PermissionDenied(message)

        confirmation = serializer.save()
        return Response(
            self.get_serializer(confirmation).data,
            status=status.HTTP_200_OK,
        )

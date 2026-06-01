from academics.api.views import AcademicYearViewSet
from academics.api.views import CalendarDocumentCurrentView
from academics.api.views import GradeSubjectViewSet
from academics.api.views import GradeViewSet
from academics.api.views import SectionViewSet
from academics.api.views import SubjectViewSet
from accounts.api.views import UserViewSet
from analytics.api.views import InterventionLogViewSet
from announcements.api.views import AnnouncementViewSet
from assessments.api.views import AssessmentResultViewSet
from assessments.api.views import AssessmentViewSet
from assessments.api.views import HomeworkConfirmationViewSet
from attendance.api.views import AttendanceReasonViewSet
from attendance.api.views import AttendanceSummaryViewSet
from attendance.api.views import AttendanceViewSet
from branches.api.views import BranchAdminCompleteInvitationView
from branches.api.views import BranchAdminInviteView
from branches.api.views import BranchAdminViewSet
from branches.api.views import BranchViewSet
from django.conf import settings
from django.urls import include
from django.urls import path
from messaging.api.urls import urlpatterns as messaging_urlpatterns
from organizations.api.views import OrganizationViewSet
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter
from schools.api.views import SchoolViewSet
from students.api.views import ParentCompleteInvitationView
from students.api.views import ParentInvitationOtpRequestView
from students.api.views import ParentInvitationOtpVerifyView
from students.api.views import ParentInviteView
from students.api.views import ParentStudentLinkViewSet
from students.api.views import ParentViewSet
from students.api.views import StudentViewSet
from teachers.api.views import HomeroomAssignmentViewSet
from teachers.api.views import TeacherCompleteInvitationView
from teachers.api.views import TeacherInviteView
from teachers.api.views import TeacherQualificationViewSet
from teachers.api.views import TeacherSubjectAssignmentViewSet
from teachers.api.views import TeacherViewSet

from core.api.views import ImportStatusView

router = DefaultRouter() if settings.DEBUG else SimpleRouter()


router.register("users", UserViewSet)
router.register("organizations", OrganizationViewSet)
router.register("schools", SchoolViewSet)
router.register("branches", BranchViewSet)
router.register("branch-admins", BranchAdminViewSet)
router.register("academic-years", AcademicYearViewSet)
router.register("grades", GradeViewSet)
router.register("grade-subjects", GradeSubjectViewSet, basename="grade-subject")
router.register("sections", SectionViewSet)
router.register("subjects", SubjectViewSet)
router.register("students", StudentViewSet, basename="student")
router.register("parents", ParentViewSet, basename="parent")
router.register("parent-links", ParentStudentLinkViewSet, basename="parent-link")
router.register("teachers", TeacherViewSet, basename="teacher")
router.register(
    "teacher-qualifications",
    TeacherQualificationViewSet,
    basename="teacher-qualification",
)
router.register(
    "teacher-assignments",
    TeacherSubjectAssignmentViewSet,
    basename="teacher-assignment",
)
router.register(
    "homeroom-assignments",
    HomeroomAssignmentViewSet,
    basename="homeroom-assignment",
)
router.register("attendance", AttendanceViewSet, basename="attendance")
router.register(
    "attendance-reasons",
    AttendanceReasonViewSet,
    basename="attendance-reason",
)
router.register(
    "attendance-summaries",
    AttendanceSummaryViewSet,
    basename="attendance-summary",
)
router.register(
    "intervention-logs",
    InterventionLogViewSet,
    basename="intervention-log",
)
router.register("assessments", AssessmentViewSet, basename="assessment")
router.register(
    "assessment-results",
    AssessmentResultViewSet,
    basename="assessment-result",
)
router.register(
    "homework-confirmations",
    HomeworkConfirmationViewSet,
    basename="homework-confirmation",
)
router.register("announcements", AnnouncementViewSet, basename="announcement")

app_name = "api"
urlpatterns = [
    path(
        "calendar-documents/current/",
        CalendarDocumentCurrentView.as_view(),
        name="calendar-document-current",
    ),
    path(
        "branch-admins/invite/",
        BranchAdminInviteView.as_view(),
        name="branch-admin-invite",
    ),
    path(
        "branch-admins/complete-invitation/",
        BranchAdminCompleteInvitationView.as_view(),
        name="branch-admin-complete-invitation",
    ),
    path(
        "teachers/invite/",
        TeacherInviteView.as_view(),
        name="teacher-invite",
    ),
    path(
        "teachers/complete-invitation/",
        TeacherCompleteInvitationView.as_view(),
        name="teacher-complete-invitation",
    ),
    path(
        "parents/invite/",
        ParentInviteView.as_view(),
        name="parent-invite",
    ),
    path(
        "parents/complete-invitation/",
        ParentCompleteInvitationView.as_view(),
        name="parent-complete-invitation",
    ),
    path(
        "parents/request-invitation-otp/",
        ParentInvitationOtpRequestView.as_view(),
        name="parent-request-invitation-otp",
    ),
    path(
        "parents/verify-invitation-otp/",
        ParentInvitationOtpVerifyView.as_view(),
        name="parent-verify-invitation-otp",
    ),
    path(
        "import-status/<str:task_id>/",
        ImportStatusView.as_view(),
        name="import-status",
    ),
    *router.urls,
    path("", include("media.api.urls")),
    *messaging_urlpatterns,
]

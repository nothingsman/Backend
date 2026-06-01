from datetime import date

import pytest
from academics.tests.factories import AcademicYearFactory
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from academics.tests.factories import SubjectFactory
from announcements.models import Announcement
from announcements.models import AnnouncementSection
from announcements.tests.factories import AnnouncementFactory
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.models import Attendance
from attendance.tasks import notify_parent_of_absence
from messaging.tests.factories import ChatMessageFactory
from messaging.tests.factories import TeacherFactory
from notifications.models import Notification
from students.tests.factories import ParentFactory
from students.tests.factories import ParentStudentLinkFactory
from students.tests.factories import StudentFactory
from teachers.models import TeacherSubjectAssignment

EXPECTED_PERCENTAGE = 80.0


def _build_section_context():
    parent = ParentFactory()
    organization = parent.organizations.first()
    branch = parent.branches.first()
    academic_year = AcademicYearFactory(
        organization=organization,
        branch=branch,
        is_current=True,
    )
    grade = GradeFactory(
        organization=organization,
        branch=branch,
    )
    section = SectionFactory(
        organization=organization,
        branch=branch,
        grade=grade,
        academic_year=academic_year,
    )
    student = StudentFactory(
        organization=organization,
        branch=branch,
        current_section=section,
    )
    ParentStudentLinkFactory(parent=parent, student=student)
    teacher = TeacherFactory(_student=student)
    subject = SubjectFactory(
        organization=organization,
        branch=branch,
        grade=grade,
    )
    teacher_assignment = TeacherSubjectAssignment.objects.create(
        teacher=teacher,
        organization=organization,
        subject=subject,
        section=section,
        academic_year=academic_year,
    )
    return {
        "parent": parent,
        "teacher": teacher,
        "student": student,
        "section": section,
        "subject": subject,
        "teacher_assignment": teacher_assignment,
        "organization": organization,
        "branch": branch,
    }


@pytest.mark.django_db
def test_announcement_signal_creates_notifications_for_expected_recipients(
    django_capture_on_commit_callbacks,
):
    context = _build_section_context()

    with django_capture_on_commit_callbacks(execute=True):
        announcement = AnnouncementFactory(
            organization=context["student"].organization,
            branch=context["student"].branch,
            status=Announcement.StatusChoices.SENT,
            target_roles=Announcement.TargetRoleChoices.BOTH,
        )
    AnnouncementSection.objects.create(
        announcement=announcement,
        section=context["section"],
    )

    recipient_ids = set(
        Notification.objects.filter(notifiable_id=str(announcement.id)).values_list(
            "recipient_id",
            flat=True,
        ),
    )
    assert recipient_ids == {
        context["parent"].user_id,
        context["teacher"].user_id,
    }


@pytest.mark.django_db
def test_announcement_transition_to_sent_notifies_once(
    django_capture_on_commit_callbacks,
):
    context = _build_section_context()
    announcement = AnnouncementFactory(
        organization=context["student"].organization,
        branch=context["student"].branch,
        status=Announcement.StatusChoices.DRAFT,
        target_roles=Announcement.TargetRoleChoices.PARENTS,
    )
    AnnouncementSection.objects.create(
        announcement=announcement,
        section=context["section"],
    )

    assert Notification.objects.filter(notifiable_id=str(announcement.id)).count() == 0

    with django_capture_on_commit_callbacks(execute=True):
        announcement.status = Announcement.StatusChoices.SENT
        announcement.save(update_fields=["status", "updated_at"])

    notifications = Notification.objects.filter(notifiable_id=str(announcement.id))
    assert notifications.count() == 1
    assert notifications.get().recipient_id == context["parent"].user_id

    announcement.subject = "Edited subject"
    announcement.save(update_fields=["subject", "updated_at"])

    assert Notification.objects.filter(notifiable_id=str(announcement.id)).count() == 1


@pytest.mark.django_db
def test_chat_message_signal_notifies_the_other_participant_only():
    message = ChatMessageFactory()

    notifications = Notification.objects.filter(notifiable_id=str(message.id))
    assert notifications.count() == 1
    notification = notifications.get()
    assert notification.recipient_id == message.thread.teacher.user_id
    assert notification.data["thread_id"] == str(message.thread_id)


@pytest.mark.django_db
def test_assessment_publish_notifications_cover_create_and_transition_without_duplicates(  # noqa: E501
    django_capture_on_commit_callbacks,
):
    context = _build_section_context()

    with django_capture_on_commit_callbacks(execute=True):
        published_assessment = Assessment.objects.create(
            organization=context["organization"],
            branch=context["branch"],
            teacher_assignment=context["teacher_assignment"],
            title="Fractions Worksheet",
            task_type=Assessment.TaskType.ASSIGNMENT,
            description="Complete the sheet",
            total_marks=20,
            due_date=date(2026, 6, 4),
            status=Assessment.Status.PUBLISHED,
        )

    notifications = Notification.objects.filter(
        notifiable_id=str(published_assessment.id),
    )
    assert notifications.count() == 1
    notification = notifications.get()
    assert notification.recipient_id == context["parent"].user_id
    assert notification.data["category"] == "assignment"
    assert notification.data["student_id"] == str(context["student"].id)

    draft_assessment = Assessment.objects.create(
        organization=context["organization"],
        branch=context["branch"],
        teacher_assignment=context["teacher_assignment"],
        title="Decimals Quiz",
        task_type=Assessment.TaskType.QUIZ,
        description="Quiz",
        total_marks=10,
        due_date=date(2026, 6, 5),
        status=Assessment.Status.DRAFT,
    )
    assert (
        Notification.objects.filter(
            notifiable_id=str(draft_assessment.id),
        ).count()
        == 0
    )

    with django_capture_on_commit_callbacks(execute=True):
        draft_assessment.status = Assessment.Status.PUBLISHED
        draft_assessment.save(update_fields=["status", "updated_at"])
    assert (
        Notification.objects.filter(
            notifiable_id=str(draft_assessment.id),
        ).count()
        == 1
    )

    draft_assessment.description = "Edited"
    draft_assessment.save(update_fields=["description", "updated_at"])
    assert (
        Notification.objects.filter(
            notifiable_id=str(draft_assessment.id),
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_assessment_grade_notifications_fire_once_for_first_grading(
    django_capture_on_commit_callbacks,
):
    context = _build_section_context()
    with django_capture_on_commit_callbacks(execute=True):
        assessment = Assessment.objects.create(
            organization=context["organization"],
            branch=context["branch"],
            teacher_assignment=context["teacher_assignment"],
            title="Numbers Quiz",
            task_type=Assessment.TaskType.QUIZ,
            description="Quiz",
            total_marks=10,
            passing_marks=5,
            due_date=date(2026, 6, 5),
            status=Assessment.Status.PUBLISHED,
        )
    result = AssessmentResult.objects.create(
        organization=context["organization"],
        assessment=assessment,
        student=context["student"],
        submission_status=AssessmentResult.SubmissionStatus.PENDING,
    )

    Notification.objects.filter(notifiable_id=str(assessment.id)).delete()

    with django_capture_on_commit_callbacks(execute=True):
        result.obtained_marks = 8
        result.submission_status = AssessmentResult.SubmissionStatus.GRADED
        result.save(
            update_fields=["obtained_marks", "submission_status", "updated_at"],
        )

    notifications = Notification.objects.filter(notifiable_id=str(result.id))
    assert notifications.count() == 1
    notification = notifications.get()
    assert notification.recipient_id == context["parent"].user_id
    assert notification.data["category"] == "grade"
    assert notification.data["percentage"] == EXPECTED_PERCENTAGE

    result.feedback = "Nice work"
    result.save(update_fields=["feedback", "updated_at"])

    assert Notification.objects.filter(notifiable_id=str(result.id)).count() == 1


@pytest.mark.django_db
def test_attendance_notifications_cover_absent_late_and_are_idempotent():
    context = _build_section_context()

    absent = Attendance.objects.create(
        organization=context["organization"],
        branch=context["branch"],
        academic_year=context["teacher_assignment"].academic_year,
        section=context["section"],
        student=context["student"],
        recorded_by=context["teacher"].user,
        date=date(2026, 6, 2),
        status=Attendance.Status.ABSENT,
        remarks="Sick",
    )
    notify_parent_of_absence.run(str(absent.id))
    notify_parent_of_absence.run(str(absent.id))

    absent_notifications = Notification.objects.filter(notifiable_id=str(absent.id))
    assert absent_notifications.count() == 1
    assert absent_notifications.get().data["category"] == "attendance"

    late = Attendance.objects.create(
        organization=context["organization"],
        branch=context["branch"],
        academic_year=context["teacher_assignment"].academic_year,
        section=context["section"],
        student=context["student"],
        recorded_by=context["teacher"].user,
        date=date(2026, 6, 3),
        status=Attendance.Status.LATE,
    )
    notify_parent_of_absence.run(str(late.id))
    assert Notification.objects.filter(notifiable_id=str(late.id)).count() == 1

    present = Attendance.objects.create(
        organization=context["organization"],
        branch=context["branch"],
        academic_year=context["teacher_assignment"].academic_year,
        section=context["section"],
        student=context["student"],
        recorded_by=context["teacher"].user,
        date=date(2026, 6, 4),
        status=Attendance.Status.PRESENT,
    )
    notify_parent_of_absence.run(str(present.id))
    assert Notification.objects.filter(notifiable_id=str(present.id)).count() == 0

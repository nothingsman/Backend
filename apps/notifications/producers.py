from __future__ import annotations

from typing import TYPE_CHECKING

from announcements.models import Announcement
from attendance.models import Attendance
from django.db.models import Q
from notifications.services import create_notification
from notifications.services import create_notification_once
from students.models import ParentStudentLink
from students.models import Student
from teachers.models import Teacher

if TYPE_CHECKING:
    from assessments.models import Assessment
    from assessments.models import AssessmentResult
    from messaging.models import ChatMessage
    from notifications.models import Notification


def _get_announcement_parent_users(announcement: Announcement):
    links = ParentStudentLink.objects.select_related("parent__user", "student").filter(
        student__organization=announcement.organization,
        student__branch=announcement.branch,
        parent__is_active=True,
    )

    section_ids = list(
        announcement.targeted_sections.values_list("section_id", flat=True),
    )
    grade_ids = list(
        announcement.targeted_grades.values_list("grade_id", flat=True),
    )

    if section_ids:
        links = links.filter(student__current_section_id__in=section_ids)
    elif grade_ids:
        links = links.filter(student__current_section__grade_id__in=grade_ids)

    return {link.parent.user for link in links.distinct()}


def _get_announcement_teacher_users(announcement: Announcement):
    teachers = Teacher.objects.select_related("user").filter(
        organization=announcement.organization,
        branch=announcement.branch,
    )

    section_ids = list(
        announcement.targeted_sections.values_list("section_id", flat=True),
    )
    grade_ids = list(
        announcement.targeted_grades.values_list("grade_id", flat=True),
    )

    if section_ids:
        teachers = teachers.filter(
            Q(subject_assignments__section_id__in=section_ids)
            | Q(homeroom_assignments__section_id__in=section_ids),
        )
    elif grade_ids:
        teachers = teachers.filter(
            Q(subject_assignments__section__grade_id__in=grade_ids)
            | Q(homeroom_assignments__section__grade_id__in=grade_ids),
        )

    return {teacher.user for teacher in teachers.distinct()}


def _get_active_parent_users_for_student(student: Student):
    links = ParentStudentLink.objects.select_related("parent__user").filter(
        student=student,
        parent__is_active=True,
    )
    return {link.parent.user for link in links}


def create_announcement_notifications(announcement: Announcement) -> list[Notification]:
    recipients = set()
    if announcement.target_roles in [
        Announcement.TargetRoleChoices.PARENTS,
        Announcement.TargetRoleChoices.BOTH,
    ]:
        recipients.update(_get_announcement_parent_users(announcement))
    if announcement.target_roles in [
        Announcement.TargetRoleChoices.TEACHERS,
        Announcement.TargetRoleChoices.BOTH,
    ]:
        recipients.update(_get_announcement_teacher_users(announcement))

    data = {
        "category": "announcement",
        "is_urgent": announcement.is_urgent,
        "branch_id": str(announcement.branch_id),
        "organization_id": str(announcement.organization_id),
        "grade_ids": [
            str(grade_id)
            for grade_id in announcement.targeted_grades.values_list(
                "grade_id",
                flat=True,
            )
        ],
        "section_ids": [
            str(section_id)
            for section_id in announcement.targeted_sections.values_list(
                "section_id",
                flat=True,
            )
        ],
    }

    return [
        create_notification_once(
            recipient=recipient,
            notifiable=announcement,
            title=announcement.subject,
            message=announcement.message,
            event_key=f"announcement.sent:{announcement.id}",
            data=data,
        )
        for recipient in recipients
    ]


def create_chat_message_notification(message: ChatMessage):
    thread = message.thread
    recipient = (
        thread.teacher.user
        if message.sender_id == thread.parent.user_id
        else thread.parent.user
    )

    if recipient.id == message.sender_id:
        return None

    sender_name = message.sender.name or message.sender.email or "New message"
    return create_notification(
        recipient=recipient,
        notifiable=message,
        title="New chat message",
        message=message.text or f"{sender_name} sent an attachment",
        data={
            "category": "message",
            "thread_id": str(thread.id),
            "sender_id": str(message.sender_id),
            "student_id": str(thread.student_id),
            "branch_id": str(thread.branch_id),
            "organization_id": str(thread.organization_id),
        },
    )


def create_assessment_published_notifications(
    assessment: Assessment,
) -> list[Notification]:
    students = Student.objects.filter(
        organization_id=assessment.organization_id,
        branch_id=assessment.branch_id,
        current_section_id=assessment.section.id,
    )
    due_date = assessment.due_date.isoformat() if assessment.due_date else None
    due_text = f" Due: {assessment.due_date}." if assessment.due_date else ""
    notifications = []

    for student in students:
        data = {
            "category": "assignment",
            "task_type": assessment.task_type,
            "assessment_id": str(assessment.id),
            "student_id": str(student.id),
            "section_id": str(assessment.section.id),
            "subject_id": str(assessment.subject.id),
            "branch_id": str(assessment.branch_id),
            "organization_id": str(assessment.organization_id),
            "due_date": due_date,
        }
        notifications.extend(
            [
                create_notification_once(
                    recipient=recipient,
                    notifiable=assessment,
                    title=(
                        f"New {assessment.get_task_type_display()}: {assessment.title}"
                    ),
                    message=(
                        f"{student.first_name} has a new "
                        f"{assessment.get_task_type_display().lower()} in "
                        f"{assessment.subject.name}.{due_text}"
                    ),
                    event_key=f"assessment.published:{assessment.id}:{student.id}",
                    data=data,
                )
                for recipient in _get_active_parent_users_for_student(student)
            ],
        )
    return notifications


def create_assessment_graded_notifications(
    result: AssessmentResult,
) -> list[Notification]:
    assessment = result.assessment
    score_text = (
        f"{result.obtained_marks}/{assessment.total_marks}"
        if result.obtained_marks is not None
        else "graded"
    )
    data = {
        "category": "grade",
        "assessment_result_id": str(result.id),
        "assessment_id": str(assessment.id),
        "student_id": str(result.student_id),
        "subject_id": str(assessment.subject.id),
        "section_id": str(assessment.section.id),
        "branch_id": str(assessment.branch_id),
        "organization_id": str(assessment.organization_id),
        "obtained_marks": str(result.obtained_marks)
        if result.obtained_marks is not None
        else None,
        "total_marks": str(assessment.total_marks),
        "percentage": result.percentage,
        "is_below_passing": result.is_below_passing,
    }

    return [
        create_notification_once(
            recipient=recipient,
            notifiable=result,
            title=f"{assessment.get_task_type_display()} Graded",
            message=(
                f"{result.student.first_name}'s {assessment.title} was graded: "
                f"{score_text}."
            ),
            event_key=f"assessment.graded:{result.id}",
            data=data,
        )
        for recipient in _get_active_parent_users_for_student(result.student)
    ]


def create_attendance_status_notifications(
    attendance: Attendance,
) -> list[Notification]:
    if attendance.status not in [Attendance.Status.ABSENT, Attendance.Status.LATE]:
        return []

    title = (
        "Absence Recorded"
        if attendance.status == Attendance.Status.ABSENT
        else "Late Arrival Recorded"
    )
    remarks = f" Remarks: {attendance.remarks}" if attendance.remarks else ""
    data = {
        "category": "attendance",
        "attendance_id": str(attendance.id),
        "student_id": str(attendance.student_id),
        "section_id": str(attendance.section_id),
        "branch_id": str(attendance.branch_id),
        "organization_id": str(attendance.organization_id),
        "date": attendance.date.isoformat(),
        "status": attendance.status,
    }

    return [
        create_notification_once(
            recipient=recipient,
            notifiable=attendance,
            title=title,
            message=(
                f"{attendance.student.first_name} was marked "
                f"{attendance.get_status_display().lower()} on {attendance.date} "
                f"for section {attendance.section.name}.{remarks}"
            ),
            event_key=f"attendance.status:{attendance.id}:{attendance.status}",
            data=data,
        )
        for recipient in _get_active_parent_users_for_student(attendance.student)
    ]

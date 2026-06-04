# ruff: noqa: C901, E501, EM101, PERF401, PLR0912, PLR0913, PLR2004, S106, S311, TRY003
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from decimal import Decimal

from academics.models import AcademicYear
from academics.models import Grade
from academics.models import GradeSubject
from academics.models import Section
from academics.models import Subject
from accounts.models import User
from analytics.models import InterventionLog
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.models import Attendance
from attendance.models import AttendanceReason
from attendance.models import AttendanceSummary
from branches.models import Branch
from branches.models import BranchAdmin
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone
from organizations.models import Organization
from schools.models import School
from students.models import Parent
from students.models import ParentStudentLink
from students.models import Student
from students.models import StudentAcademicYearSection
from teachers.models import HomeroomAssignment
from teachers.models import Teacher
from teachers.models import TeacherSubjectAssignment


@dataclass(frozen=True)
class StudentSeedRecord:
    student: Student
    parent: Parent
    homeroom_teacher: Teacher


class Command(BaseCommand):
    help = (
        "Populate a dedicated demo organization with one month of attendance "
        "and assessment data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of trailing calendar days to seed. Default: 30.",
        )
        parser.add_argument(
            "--students-per-section",
            type=int,
            default=10,
            help="Students to create in each section. Default: 10.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Random seed for reproducible demo data. Default: 42.",
        )
        parser.add_argument(
            "--owner-email",
            default="seed-owner@example.com",
            help="Owner email for the seeded demo organization.",
        )
        parser.add_argument(
            "--organization-name",
            default="One Month Demo Organization",
            help="Organization name for the seeded dataset.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        days = options["days"]
        students_per_section = options["students_per_section"]
        seed = options["seed"]
        owner_email = options["owner_email"]
        organization_name = options["organization_name"]

        if days < 7:
            raise CommandError("--days must be at least 7.")
        if students_per_section < 1:
            raise CommandError("--students-per-section must be at least 1.")

        rng = random.Random(seed)
        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=days - 1)
        school_days = [
            start_date + timedelta(days=offset)
            for offset in range(days)
            if (start_date + timedelta(days=offset)).weekday() < 5
        ]
        if not school_days:
            raise CommandError("The selected date range contains no weekdays to seed.")

        owner = self._get_or_create_user(
            email=owner_email,
            role=User.Role.ORGANIZATION,
            name="Seed Owner",
            phone_number="+251900000001",
            password="seedpass123",
        )
        self._reset_existing_organization(
            owner=owner,
            organization_name=organization_name,
        )

        organization = Organization.objects.create(
            owner=owner,
            name=organization_name,
            trade_name="One Month Demo",
            tin_number="1000000001",
            license_no="SEED-LICENSE-001",
            client_full_name="Seed Owner",
            business_address="Addis Ababa, Ethiopia",
            business_phone_number="+251911000001",
            client_phone_number="+251922000001",
            status=Organization.Status.ACTIVE,
            verification_status=Organization.VerificationStatus.VERIFIED,
            verification_failure_reason="",
            verification_match_source="seed-script",
            verified_name=organization_name,
            verified_license_no="SEED-LICENSE-001",
            verified_tin_number="1000000001",
        )
        school = School.objects.create(
            organization=organization,
            name="Kelem Demo School",
            description="Seeded school for one month demo data.",
            country="Ethiopia",
            contact_email="school.seed@example.com",
            contact_phone="+251933000001",
            website="https://example.com/demo-school",
            status=School.Status.ACTIVE,
        )
        branch = Branch.objects.create(
            organization=organization,
            school=school,
            name="Main Campus",
            address="Bole, Addis Ababa",
            city="Addis Ababa",
            region="Addis Ababa",
            contact_phone="+251944000001",
            contact_email="main-campus@example.com",
            status=Branch.Status.ACTIVE,
        )

        branch_admin_user = self._get_or_create_user(
            email="branch-admin.seed@example.com",
            role=User.Role.BRANCH_ADMIN,
            name="Branch Admin",
            phone_number="+251900000002",
            password="seedpass123",
        )
        BranchAdmin.objects.create(
            organization=organization,
            branch=branch,
            user=branch_admin_user,
            emergency_contact_name="Branch Admin Contact",
            emergency_contact_phone="+251955000001",
            role_title="Campus Administrator",
            qualification="BA in Educational Leadership",
            status=BranchAdmin.Status.ACTIVE,
        )

        academic_year = AcademicYear.objects.create(
            organization=organization,
            branch=branch,
            name=f"{start_date.year}/{end_date.year}",
            start_date=start_date,
            end_date=end_date,
            is_current=True,
        )

        grades = self._create_grades_and_sections(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
        )
        teacher_assignments, homeroom_by_section = (
            self._create_teachers_and_assignments(
                organization=organization,
                branch=branch,
                academic_year=academic_year,
                sections=grades["sections"],
                subjects_by_grade=grades["subjects_by_grade"],
            )
        )
        students = self._create_students_and_parents(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            sections=grades["sections"],
            homeroom_by_section=homeroom_by_section,
            students_per_section=students_per_section,
        )

        attendance_count, reason_count = self._create_attendance_data(
            rng=rng,
            academic_year=academic_year,
            school_days=school_days,
            students=students,
            branch=branch,
            organization=organization,
        )
        assessment_count, result_count, intervention_count = (
            self._create_assessment_data(
                rng=rng,
                academic_year=academic_year,
                school_days=school_days,
                teacher_assignments=teacher_assignments,
                students=students,
                organization=organization,
                branch=branch,
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded one-month demo data: "
                f"organization=1, sections={len(grades['sections'])}, "
                f"students={len(students)}, attendance={attendance_count}, "
                f"attendance_reasons={reason_count}, assessments={assessment_count}, "
                f"results={result_count}, interventions={intervention_count}.",
            ),
        )

    def _reset_existing_organization(
        self,
        *,
        owner: User,
        organization_name: str,
    ) -> None:
        Organization.objects.filter(
            owner=owner,
            name=organization_name,
        ).delete()

    def _get_or_create_user(
        self,
        *,
        email: str,
        role: str,
        name: str,
        phone_number: str,
        password: str,
    ) -> User:
        user = User.objects.by_email(email).first()
        if user is None:
            return User.objects.create_user(
                email=email,
                password=password,
                role=role,
                name=name,
                phone_number=phone_number,
                is_active=True,
            )

        user.role = role
        user.name = name
        user.phone_number = phone_number
        user.is_active = True
        user.set_password(password)
        user.save(
            update_fields=[
                "role",
                "name",
                "phone_number",
                "password",
                "is_active",
            ],
        )
        return user

    def _create_grades_and_sections(
        self,
        *,
        organization: Organization,
        branch: Branch,
        academic_year: AcademicYear,
    ) -> dict[str, list | dict]:
        grade_specs = [
            (7, "Grade 7"),
            (8, "Grade 8"),
            (9, "Grade 9"),
        ]
        subject_specs = [
            ("Mathematics", "MATH"),
            ("English", "ENG"),
            ("Biology", "BIO"),
            ("ICT", "ICT"),
        ]

        grades: list[Grade] = []
        sections: list[Section] = []
        subjects_by_grade: dict[str, list[Subject]] = {}

        for level, grade_name in grade_specs:
            grade = Grade.objects.create(
                organization=organization,
                branch=branch,
                name=grade_name,
                level=level,
            )
            grades.append(grade)

            section_a = Section.objects.create(
                organization=organization,
                branch=branch,
                grade=grade,
                academic_year=academic_year,
                name="A",
            )
            section_b = Section.objects.create(
                organization=organization,
                branch=branch,
                grade=grade,
                academic_year=academic_year,
                name="B",
            )
            sections.extend([section_a, section_b])

            grade_subjects: list[Subject] = []
            for subject_name, code_prefix in subject_specs:
                subject = Subject.objects.create(
                    organization=organization,
                    branch=branch,
                    grade=grade,
                    name=subject_name,
                    code=f"{code_prefix}-{level}",
                )
                GradeSubject.objects.create(
                    organization=organization,
                    grade=grade,
                    subject=subject,
                )
                grade_subjects.append(subject)
            subjects_by_grade[grade.name] = grade_subjects

        return {
            "grades": grades,
            "sections": sections,
            "subjects_by_grade": subjects_by_grade,
        }

    def _create_teachers_and_assignments(
        self,
        *,
        organization: Organization,
        branch: Branch,
        academic_year: AcademicYear,
        sections: list[Section],
        subjects_by_grade: dict[str, list[Subject]],
    ) -> tuple[list[TeacherSubjectAssignment], dict[str, Teacher]]:
        teacher_specs = [
            (
                "math-teacher.seed@example.com",
                "Mathematics Teacher",
                "TCH-MATH",
                "Mathematics",
            ),
            (
                "english-teacher.seed@example.com",
                "English Teacher",
                "TCH-ENG",
                "English",
            ),
            (
                "biology-teacher.seed@example.com",
                "Biology Teacher",
                "TCH-BIO",
                "Biology",
            ),
            ("ict-teacher.seed@example.com", "ICT Teacher", "TCH-ICT", "ICT"),
        ]

        teachers_by_subject: dict[str, Teacher] = {}
        for index, (email, name, employee_id, specialization) in enumerate(
            teacher_specs,
            start=3,
        ):
            user = self._get_or_create_user(
                email=email,
                role=User.Role.TEACHER,
                name=name,
                phone_number=f"+2519000000{index}",
                password="seedpass123",
            )
            teacher = Teacher.objects.create(
                user=user,
                organization=organization,
                branch=branch,
                employee_id=employee_id,
                specialization=specialization,
                joining_date=academic_year.start_date - timedelta(days=120),
                bio=f"{specialization} teacher for demo data.",
            )
            teachers_by_subject[specialization] = teacher

        assignments: list[TeacherSubjectAssignment] = []
        homeroom_by_section: dict[str, Teacher] = {}
        rotation = list(teachers_by_subject.values())

        for index, section in enumerate(sections):
            for subject in subjects_by_grade[section.grade.name]:
                assignments.append(
                    TeacherSubjectAssignment(
                        teacher=teachers_by_subject[subject.name],
                        organization=organization,
                        subject=subject,
                        section=section,
                        academic_year=academic_year,
                    ),
                )
            homeroom_teacher = rotation[index % len(rotation)]
            homeroom_by_section[str(section.id)] = homeroom_teacher
            HomeroomAssignment.objects.create(
                organization=organization,
                branch=branch,
                academic_year=academic_year,
                section=section,
                teacher=homeroom_teacher,
                notes="Seeded homeroom assignment.",
            )

        TeacherSubjectAssignment.objects.bulk_create(assignments, batch_size=200)
        return assignments, homeroom_by_section

    def _create_students_and_parents(
        self,
        *,
        organization: Organization,
        branch: Branch,
        academic_year: AcademicYear,
        sections: list[Section],
        homeroom_by_section: dict[str, Teacher],
        students_per_section: int,
    ) -> list[StudentSeedRecord]:
        first_names = [
            "Abel",
            "Beth",
            "Caleb",
            "Desta",
            "Eden",
            "Fikir",
            "Hana",
            "Isaac",
            "Jemal",
            "Liya",
            "Meron",
            "Noah",
        ]
        last_names = [
            "Bekele",
            "Demissie",
            "Fekadu",
            "Gebre",
            "Haile",
            "Kassa",
            "Lema",
            "Mekonen",
            "Nigatu",
            "Tesfaye",
        ]

        students: list[StudentSeedRecord] = []

        for section_index, section in enumerate(sections, start=1):
            for student_index in range(1, students_per_section + 1):
                serial = (section_index - 1) * students_per_section + student_index
                first_name = first_names[(serial - 1) % len(first_names)]
                last_name = last_names[(serial - 1) % len(last_names)]

                student = Student.objects.create(
                    organization=organization,
                    branch=branch,
                    first_name=first_name,
                    last_name=last_name,
                    gender=(
                        Student.Gender.MALE if serial % 2 else Student.Gender.FEMALE
                    ),
                    date_of_birth=date(
                        2012,
                        ((serial - 1) % 12) + 1,
                        ((serial - 1) % 27) + 1,
                    ),
                    roll_no=f"G{section.grade.level}{section.name}{student_index:02d}",
                    current_section=section,
                    admission_date=academic_year.start_date
                    - timedelta(days=serial % 180),
                    status=Student.Status.ACTIVE,
                )
                StudentAcademicYearSection.objects.create(
                    student=student,
                    academic_year=academic_year,
                    section=section,
                )

                parent_user = self._get_or_create_user(
                    email=f"parent-{serial}@example.com",
                    role=User.Role.PARENT,
                    name=f"{first_name} Parent",
                    phone_number=f"+251977{serial:06d}",
                    password="seedpass123",
                )
                parent, _ = Parent.objects.update_or_create(
                    user=parent_user,
                    defaults={
                        "secondary_phone_number": f"+251988{serial:06d}",
                        "occupation": "Business Owner",
                        "work_address": "Addis Ababa",
                        "relationship_notes": "Seeded parent profile.",
                        "emergency_contact_name": f"{last_name} Guardian",
                        "emergency_contact_phone": f"+251966{serial:06d}",
                        "is_active": True,
                    },
                )
                parent.organizations.set([organization])
                parent.branches.set([branch])
                ParentStudentLink.objects.create(
                    student=student,
                    parent=parent,
                    relationship_type=ParentStudentLink.Relationship.GUARDIAN,
                    is_primary_contact=True,
                )

                students.append(
                    StudentSeedRecord(
                        student=student,
                        parent=parent,
                        homeroom_teacher=homeroom_by_section[str(section.id)],
                    ),
                )

        return students

    def _create_attendance_data(
        self,
        *,
        rng: random.Random,
        academic_year: AcademicYear,
        school_days: list[date],
        students: list[StudentSeedRecord],
        branch: Branch,
        organization: Organization,
    ) -> tuple[int, int]:
        attendance_rows: list[Attendance] = []
        parent_user_by_student_id = {
            str(record.student.id): record.parent.user for record in students
        }
        summary_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "PRESENT": 0,
                "ABSENT": 0,
                "LATE": 0,
                "EXCUSED": 0,
                "TOTAL": 0,
            },
        )

        for school_day in school_days:
            for record in students:
                status = rng.choices(
                    population=[
                        Attendance.Status.PRESENT,
                        Attendance.Status.LATE,
                        Attendance.Status.ABSENT,
                        Attendance.Status.EXCUSED,
                    ],
                    weights=[84, 8, 5, 3],
                    k=1,
                )[0]
                remarks = ""
                if status == Attendance.Status.ABSENT:
                    remarks = "Marked absent during morning homeroom."
                elif status == Attendance.Status.LATE:
                    remarks = "Arrived after first bell."
                elif status == Attendance.Status.EXCUSED:
                    remarks = "Excused absence recorded by school."

                attendance_rows.append(
                    Attendance(
                        organization=organization,
                        branch=branch,
                        academic_year=academic_year,
                        section=record.student.current_section,
                        student=record.student,
                        recorded_by=record.homeroom_teacher.user,
                        date=school_day,
                        status=status,
                        remarks=remarks,
                    ),
                )
                student_summary = summary_counts[str(record.student.id)]
                student_summary[status] += 1
                student_summary["TOTAL"] += 1

        Attendance.objects.bulk_create(attendance_rows, batch_size=1000)

        reason_rows: list[AttendanceReason] = []
        for attendance in attendance_rows:
            if attendance.status == Attendance.Status.PRESENT:
                continue
            parent_confirmed = (
                attendance.status != Attendance.Status.LATE or rng.random() < 0.5
            )
            confirmed_by = None
            confirmed_at = None
            if parent_confirmed:
                parent_user = parent_user_by_student_id[str(attendance.student_id)]
                confirmed_by = parent_user
                confirmed_at = datetime.combine(
                    attendance.date,
                    time(hour=18, minute=15),
                    tzinfo=UTC,
                )

            category = {
                Attendance.Status.ABSENT: AttendanceReason.Category.SICKNESS,
                Attendance.Status.LATE: AttendanceReason.Category.TRANSPORTATION,
                Attendance.Status.EXCUSED: AttendanceReason.Category.FAMILY_ISSUE,
            }[attendance.status]
            reason_rows.append(
                AttendanceReason(
                    organization=organization,
                    attendance=attendance,
                    reason_category=category,
                    note=f"Seeded reason for {attendance.get_status_display().lower()}.",
                    parent_confirmed=parent_confirmed,
                    confirmed_by=confirmed_by,
                    confirmed_at=confirmed_at,
                ),
            )

        AttendanceReason.objects.bulk_create(reason_rows, batch_size=1000)

        summary_rows = [
            AttendanceSummary(
                organization=organization,
                student=record.student,
                academic_year=academic_year,
                total_present=summary_counts[str(record.student.id)]["PRESENT"],
                total_absent=summary_counts[str(record.student.id)]["ABSENT"],
                total_late=summary_counts[str(record.student.id)]["LATE"],
                total_excused=summary_counts[str(record.student.id)]["EXCUSED"],
                total_school_days=summary_counts[str(record.student.id)]["TOTAL"],
            )
            for record in students
        ]
        AttendanceSummary.objects.bulk_create(summary_rows, batch_size=500)

        return len(attendance_rows), len(reason_rows)

    def _create_assessment_data(
        self,
        *,
        rng: random.Random,
        academic_year: AcademicYear,
        school_days: list[date],
        teacher_assignments: list[TeacherSubjectAssignment],
        students: list[StudentSeedRecord],
        organization: Organization,
        branch: Branch,
    ) -> tuple[int, int, int]:
        students_by_section: dict[str, list[StudentSeedRecord]] = defaultdict(list)
        for record in students:
            students_by_section[str(record.student.current_section_id)].append(record)

        anchor_indexes = [
            max(0, len(school_days) // 5),
            max(0, (len(school_days) * 2) // 5),
            max(0, (len(school_days) * 4) // 5),
        ]
        templates = [
            (
                "Homework",
                Assessment.TaskType.HOMEWORK,
                Decimal("20.00"),
                Decimal("10.00"),
            ),
            ("Quiz", Assessment.TaskType.QUIZ, Decimal("25.00"), Decimal("12.50")),
            (
                "Assignment",
                Assessment.TaskType.ASSIGNMENT,
                Decimal("40.00"),
                Decimal("20.00"),
            ),
        ]

        assessment_rows: list[Assessment] = []
        for assignment in teacher_assignments:
            for index, (label, task_type, total_marks, passing_marks) in enumerate(
                templates,
            ):
                due_date = school_days[min(anchor_indexes[index], len(school_days) - 1)]
                assessment_rows.append(
                    Assessment(
                        organization=organization,
                        branch=branch,
                        teacher_assignment=assignment,
                        title=f"{assignment.subject.name} {label} {index + 1} - {assignment.section.grade.name}{assignment.section.name}",
                        task_type=task_type,
                        description=f"Seeded {label.lower()} for {assignment.subject.name}.",
                        total_marks=total_marks,
                        passing_marks=passing_marks,
                        due_date=due_date,
                        status=Assessment.Status.PUBLISHED,
                    ),
                )

        Assessment.objects.bulk_create(assessment_rows, batch_size=500)

        result_rows: list[AssessmentResult] = []
        intervention_candidates: list[AssessmentResult] = []

        for assessment in assessment_rows:
            section_students = students_by_section[str(assessment.section.id)]
            for record in section_students:
                submission_status = rng.choices(
                    population=[
                        AssessmentResult.SubmissionStatus.GRADED,
                        AssessmentResult.SubmissionStatus.SUBMITTED,
                        AssessmentResult.SubmissionStatus.MISSING,
                    ],
                    weights=[82, 10, 8],
                    k=1,
                )[0]

                obtained_marks = None
                feedback = ""
                parent_confirmed = False
                parent_confirmed_by = None
                parent_confirmed_at = None

                if submission_status == AssessmentResult.SubmissionStatus.GRADED:
                    ratio = Decimal(str(rng.uniform(0.35, 0.98))).quantize(
                        Decimal("0.01"),
                    )
                    obtained_marks = (assessment.total_marks * ratio).quantize(
                        Decimal("0.01"),
                    )
                    feedback = "Steady progress over the last month."
                    if (
                        assessment.task_type == Assessment.TaskType.HOMEWORK
                        and rng.random() < 0.7
                    ):
                        parent_confirmed = True
                        parent_confirmed_by = record.parent.user
                        parent_confirmed_at = datetime.combine(
                            assessment.due_date or school_days[-1],
                            time(hour=20),
                            tzinfo=UTC,
                        )
                elif submission_status == AssessmentResult.SubmissionStatus.MISSING:
                    feedback = "Work not submitted."
                else:
                    feedback = "Awaiting final grading."

                result = AssessmentResult(
                    organization=organization,
                    assessment=assessment,
                    student=record.student,
                    graded_by=assessment.teacher.user
                    if obtained_marks is not None
                    else None,
                    obtained_marks=obtained_marks,
                    submission_status=submission_status,
                    feedback=feedback,
                    parent_confirmed=parent_confirmed,
                    parent_confirmed_by=parent_confirmed_by,
                    parent_confirmed_at=parent_confirmed_at,
                )
                result_rows.append(result)
                if (
                    obtained_marks is not None
                    and obtained_marks < assessment.passing_marks
                ):
                    intervention_candidates.append(result)

        AssessmentResult.objects.bulk_create(result_rows, batch_size=1000)

        intervention_rows: list[InterventionLog] = []
        for result in intervention_candidates:
            ratio = float(result.obtained_marks / result.assessment.passing_marks)
            if ratio < 0.5:
                severity = InterventionLog.Severity.HIGH
            elif ratio < 0.8:
                severity = InterventionLog.Severity.MEDIUM
            else:
                severity = InterventionLog.Severity.LOW

            intervention_rows.append(
                InterventionLog(
                    organization=organization,
                    student=result.student,
                    intervention_type=InterventionLog.InterventionType.LOW_GRADE,
                    severity=severity,
                    status=InterventionLog.Status.OPEN,
                    source_model="assessments.AssessmentResult",
                    source_id=result.id,
                    title=(
                        f"Low Grade Alert: {result.student.first_name} "
                        f"{result.student.last_name} in {result.assessment.subject.name}"
                    ),
                    description=(
                        f"Seeded alert for {result.obtained_marks}/{result.assessment.total_marks} "
                        f"on {result.assessment.title}."
                    ),
                ),
            )

        InterventionLog.objects.bulk_create(intervention_rows, batch_size=500)
        return len(assessment_rows), len(result_rows), len(intervention_rows)

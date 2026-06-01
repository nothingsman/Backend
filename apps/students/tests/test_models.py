import pytest
from academics.models import AcademicYear
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from branches.tests.factories import BranchFactory
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import connection
from organizations.tests.factories import OrganizationFactory
from students.models import ParentStudentLink
from students.models import StudentAcademicYearSection
from students.tests.factories import ParentFactory
from students.tests.factories import StudentFactory


@pytest.mark.django_db
def test_parent_can_belong_to_multiple_organizations_and_branches():
    expected_count = 2
    parent = ParentFactory()
    first_branch = parent.branches.first()
    first_organization = parent.organizations.first()

    second_organization = OrganizationFactory()
    second_branch = BranchFactory(school__organization=second_organization)
    second_grade = GradeFactory(
        organization=second_organization,
        branch=second_branch,
    )
    second_section = SectionFactory(
        organization=second_organization,
        branch=second_branch,
        grade=second_grade,
    )
    second_student = StudentFactory(
        organization=second_organization,
        branch=second_branch,
        current_section=second_section,
    )
    parent.organizations.add(second_student.organization)
    parent.branches.add(second_student.branch)

    parent.full_clean()

    assert parent.organizations.count() == expected_count
    assert parent.branches.count() == expected_count
    assert first_branch in parent.branches.all()
    assert first_organization in parent.organizations.all()


@pytest.mark.django_db
def test_parent_rejects_branch_outside_selected_organizations():
    parent = ParentFactory()
    invalid_student = StudentFactory()
    parent.branches.add(invalid_student.branch)

    with pytest.raises(ValidationError):
        parent.full_clean()


@pytest.mark.django_db
def test_parent_student_link_rejects_mismatched_membership():
    student = StudentFactory()
    mismatched_parent = ParentFactory()
    link = ParentStudentLink(student=student, parent=mismatched_parent)

    with pytest.raises(ValidationError):
        link.full_clean()


@pytest.mark.django_db
def test_student_academic_year_section_allows_null_section():
    organization = OrganizationFactory()
    branch = BranchFactory(school__organization=organization)
    student = StudentFactory(
        organization=organization,
        branch=branch,
        current_section=None,
    )
    academic_year = AcademicYear.objects.get(
        organization=organization,
        branch=branch,
        is_current=True,
    )

    assignment = StudentAcademicYearSection(
        student=student,
        academic_year=academic_year,
        section=None,
    )

    assignment.full_clean()
    assignment.save()

    assert assignment.section is None


@pytest.mark.django_db
def test_student_academic_year_section_rejects_mismatched_section_year():
    organization = OrganizationFactory()
    branch = BranchFactory(school__organization=organization)
    current_year = AcademicYear.objects.get(
        organization=organization,
        branch=branch,
        is_current=True,
    )
    other_year = AcademicYear.objects.create(
        organization=organization,
        branch=branch,
        name="2024/2025",
        start_date=current_year.start_date,
        end_date=current_year.end_date,
        is_current=False,
    )
    grade = GradeFactory(organization=organization, branch=branch)
    section = SectionFactory(
        organization=organization,
        branch=branch,
        grade=grade,
        academic_year=other_year,
    )
    student = StudentFactory(
        organization=organization,
        branch=branch,
        current_section=None,
    )

    assignment = StudentAcademicYearSection(
        student=student,
        academic_year=current_year,
        section=section,
    )

    with pytest.raises(ValidationError):
        assignment.full_clean()


@pytest.mark.django_db
def test_student_academic_year_section_rejects_cross_branch_or_organization():
    organization = OrganizationFactory()
    branch = BranchFactory(school__organization=organization)
    student = StudentFactory(
        organization=organization,
        branch=branch,
        current_section=None,
    )
    other_organization = OrganizationFactory()
    other_branch = BranchFactory(school__organization=other_organization)
    academic_year = AcademicYear.objects.get(
        organization=other_organization,
        branch=other_branch,
        is_current=True,
    )

    assignment = StudentAcademicYearSection(
        student=student,
        academic_year=academic_year,
    )

    with pytest.raises(ValidationError):
        assignment.full_clean()


@pytest.mark.django_db
def test_student_academic_year_section_is_unique_per_student_and_year():
    organization = OrganizationFactory()
    branch = BranchFactory(school__organization=organization)
    student = StudentFactory(
        organization=organization,
        branch=branch,
        current_section=None,
    )
    academic_year = AcademicYear.objects.get(
        organization=organization,
        branch=branch,
        is_current=True,
    )
    StudentAcademicYearSection.objects.create(
        student=student,
        academic_year=academic_year,
    )

    with pytest.raises(IntegrityError):
        StudentAcademicYearSection.objects.create(
            student=student,
            academic_year=academic_year,
        )


@pytest.mark.django_db
def test_student_pii_is_encrypted_at_rest():
    student = StudentFactory(
        first_name="Kidus",
        last_name="Alemu",
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT first_name, last_name
            FROM students_student
            WHERE id = %s
            """,
            [str(student.pk)],
        )
        encrypted_first_name, encrypted_last_name = cursor.fetchone()

    assert encrypted_first_name != "Kidus"
    assert encrypted_last_name != "Alemu"

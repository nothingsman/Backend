from pathlib import Path

import pytest
from academics.models import AcademicYear
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from branches.tests.factories import BranchFactory
from django.utils import timezone
from organizations.tests.factories import OrganizationFactory
from students.models import Student
from students.services.bulk_import import StudentBulkImportService

pytestmark = pytest.mark.django_db

EXPECTED_STUDENT_COUNT = 2


def _build_student_import_context():
    organization = OrganizationFactory()
    school = organization.schools.create(
        name="Central School",
        description="Main campus",
        country="Ethiopia",
        contact_email="school@example.com",
        contact_phone="+251900000000",
        website="https://school.example.com",
        status="ACTIVE",
    )
    branch = BranchFactory(school=school)
    academic_year = AcademicYear.objects.get(
        organization=organization,
        branch=branch,
        is_current=True,
    )
    grade = GradeFactory(organization=organization, branch=branch, name="Grade 1")
    section = SectionFactory(
        organization=organization,
        branch=branch,
        grade=grade,
        name="Section A",
        academic_year=academic_year,
    )

    return organization, branch, section


def test_student_bulk_import_creates_students() -> None:
    organization, branch, section = _build_student_import_context()

    csv_path = Path(__file__).with_name("fixtures") / "student_import_test.csv"
    content = csv_path.read_bytes()

    service = StudentBulkImportService(
        file_content=content,
        file_name=csv_path.name,
        organization_id=organization.id,
        branch_id=branch.id,
    )

    success, errors = service.run()

    assert success is True
    assert errors == []
    assert (
        Student.objects.filter(organization=organization, branch=branch).count()
        == EXPECTED_STUDENT_COUNT
    )

    alice = Student.objects.get(roll_no="STU-1001")
    assert alice.first_name == "Alice"
    assert alice.last_name == "Green"
    assert alice.gender == "FEMALE"
    assert str(alice.date_of_birth) == "2015-05-20"
    assert alice.current_section == section
    assert str(alice.admission_date) == str(timezone.now().date())

    bob = Student.objects.get(roll_no="STU-1002")
    assert bob.first_name == "Bob"
    assert bob.last_name == "Brown"
    assert bob.gender == "MALE"
    assert str(bob.date_of_birth) == "2016-06-18"
    assert bob.current_section == section
    assert str(bob.admission_date) == str(timezone.now().date())


def test_student_bulk_import_rejects_duplicate_roll_numbers_in_a_section() -> None:
    organization, branch, _section = _build_student_import_context()

    csv_content = (
        "first_name,last_name,gender,date_of_birth,section_name,grade_name,roll_no\n"
        "Alice,Green,FEMALE,2015-05-20,Section A,Grade 1,R-100\n"
        "Bob,Brown,MALE,2016-06-18,Section A,Grade 1,R-100\n"
    )

    service = StudentBulkImportService(
        file_content=csv_content.encode("utf-8"),
        file_name="students.csv",
        organization_id=organization.id,
        branch_id=branch.id,
    )

    success, errors = service.run()

    assert success is False
    assert errors == [
        {
            "row": 3,
            "errors": {
                "roll_no": ["Duplicate roll number in this section within the sheet."],
            },
        },
    ]
    assert Student.objects.filter(organization=organization, branch=branch).count() == 0

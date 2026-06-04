import pytest
from academics.models import AcademicYear
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from academics.tests.factories import SubjectFactory
from accounts.tests.factories import UserFactory
from assessments.models import Assessment
from assessments.models import AssessmentResult
from branches.tests.factories import BranchAdminFactory
from branches.tests.factories import BranchFactory
from organizations.tests.factories import OrganizationFactory
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.test import APIRequestFactory
from student_insights.models import StudentInsight
from students.api.views import ParentViewSet
from students.api.views import StudentViewSet
from students.models import Parent
from students.models import Student
from students.models import StudentAcademicYearSection
from students.tests.factories import ParentFactory
from students.tests.factories import ParentStudentLinkFactory
from students.tests.factories import StudentAcademicYearSectionFactory
from students.tests.factories import StudentBehaviourIncidentFactory
from students.tests.factories import StudentBehaviourRemarkFactory
from students.tests.factories import StudentFactory
from teachers.models import HomeroomAssignment
from teachers.models import Teacher
from teachers.models import TeacherSubjectAssignment

from media.models import StatusChoices
from media.tests.factories import MediaFileFactory

MIN_EXPECTED_MATCHED_STUDENTS = 2


@pytest.mark.django_db
class TestStudentsAPI:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def user(self):
        return UserFactory()

    @pytest.fixture
    def organization(self, user):
        return OrganizationFactory(owner=user)

    @pytest.fixture
    def branch(self, organization):
        return BranchFactory(school__organization=organization)

    @pytest.fixture
    def section(self, organization, branch):
        academic_year = AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            is_current=True,
        )
        grade = GradeFactory(organization=organization, branch=branch)
        return SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
        )

    def test_student_crud(self, api_client, user, organization, branch, section):
        api_client.force_authenticate(user=user)
        media = MediaFileFactory(
            uploaded_by=user,
            status=StatusChoices.UPLOADED,
            content_type="image/jpeg",
        )

        data = {
            "organization": str(organization.id),
            "branch": str(branch.id),
            "academic_year": str(section.academic_year_id),
            "first_name": "Alice",
            "last_name": "Smith",
            "gender": "FEMALE",
            "date_of_birth": "2015-05-20",
            "roll_no": "R101",
            "current_section": str(section.id),
            "admission_date": "2023-09-01",
            "photo": str(media.id),
            "status": "ACTIVE",
        }
        response = api_client.post("/api/students/", data)
        assert response.status_code == status.HTTP_201_CREATED
        student_id = response.data["id"]
        assert str(response.data["photo"]) == str(media.id)
        assert StudentAcademicYearSection.objects.filter(
            student_id=student_id,
            academic_year=section.academic_year,
            section=section,
        ).exists()

        response = api_client.get("/api/students/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1

        response = api_client.get(f"/api/students/{student_id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["first_name"] == "Alice"
        assert str(response.data["photo"]) == str(media.id)

        response = api_client.patch(
            f"/api/students/{student_id}/",
            {"first_name": "Alice Updated"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["first_name"] == "Alice Updated"

        response = api_client.delete(f"/api/students/{student_id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_student_list_handles_student_without_current_section(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)
        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=None,
        )
        StudentAcademicYearSectionFactory(
            student=student,
            academic_year=AcademicYear.objects.get(
                organization=organization,
                branch=branch,
                is_current=True,
            ),
            section=None,
        )

        response = api_client.get(
            f"/api/students/?branch={branch.id}&organization={organization.id}",
        )

        assert response.status_code == status.HTTP_200_OK
        result = next(
            item for item in response.data["results"] if item["id"] == str(student.id)
        )
        assert result["current_section"] is None
        assert result["section_name"] is None
        assert result["grade_id"] is None
        assert result["grade_name"] is None
        assert result["grade_level"] is None
        assert result["academic_year_id"] is None
        assert result["academic_year_name"] is None

    def test_student_list_by_academic_year_includes_year_scoped_section(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)
        student_with_section = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        StudentAcademicYearSectionFactory(
            student=student_with_section,
            academic_year=section.academic_year,
            section=section,
        )
        student_without_section = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=None,
        )
        StudentAcademicYearSectionFactory(
            student=student_without_section,
            academic_year=section.academic_year,
            section=None,
        )

        response = api_client.get(
            f"/api/students/?academic_year={section.academic_year_id}",
        )

        assert response.status_code == status.HTTP_200_OK
        results = {item["id"]: item for item in response.data["results"]}
        assert results[str(student_with_section.id)]["current_section"] == str(
            section.id,
        )
        assert results[str(student_with_section.id)]["academic_year_id"] == str(
            section.academic_year_id,
        )
        assert results[str(student_without_section.id)]["current_section"] is None
        assert results[str(student_without_section.id)]["academic_year_id"] == str(
            section.academic_year_id,
        )
        assert results[str(student_without_section.id)]["section_name"] is None

    def test_student_create_without_section_creates_year_mapping(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)
        academic_year = AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            is_current=True,
        )

        response = api_client.post(
            "/api/students/",
            {
                "organization": str(organization.id),
                "branch": str(branch.id),
                "academic_year": str(academic_year.id),
                "first_name": "No",
                "last_name": "Section",
                "gender": "MALE",
                "date_of_birth": "2015-05-20",
                "roll_no": "R102",
                "current_section": None,
                "admission_date": "2023-09-01",
                "status": "ACTIVE",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        student = Student.objects.get(id=response.data["id"])
        assert student.current_section is None
        assert StudentAcademicYearSection.objects.filter(
            student=student,
            academic_year=academic_year,
            section=None,
        ).exists()

    def test_student_patch_non_current_year_does_not_change_current_section(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)
        non_current_year = AcademicYear.objects.create(
            organization=organization,
            branch=branch,
            name="2024/2025",
            start_date=section.academic_year.start_date,
            end_date=section.academic_year.end_date,
            is_current=False,
        )
        other_section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=section.grade,
            academic_year=non_current_year,
        )
        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        StudentAcademicYearSectionFactory(
            student=student,
            academic_year=section.academic_year,
            section=section,
        )

        response = api_client.patch(
            f"/api/students/{student.id}/",
            {
                "academic_year": str(non_current_year.id),
                "current_section": str(other_section.id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        student.refresh_from_db()
        assert student.current_section == section
        assert StudentAcademicYearSection.objects.filter(
            student=student,
            academic_year=non_current_year,
            section=other_section,
        ).exists()

    def test_student_patch_current_year_syncs_current_section(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)
        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=None,
        )
        StudentAcademicYearSectionFactory(
            student=student,
            academic_year=section.academic_year,
            section=None,
        )

        response = api_client.patch(
            f"/api/students/{student.id}/",
            {
                "academic_year": str(section.academic_year_id),
                "current_section": str(section.id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        student.refresh_from_db()
        assert student.current_section == section
        assert StudentAcademicYearSection.objects.filter(
            student=student,
            academic_year=section.academic_year,
            section=section,
        ).exists()

    def test_student_read_includes_parent_full_name(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)
        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        parent = ParentFactory(
            organizations=[organization],
            branches=[branch],
        )
        parent.user.name = "Rahel"
        parent.user.father_name = "Bekele"
        parent.user.grandfather_name = "Mekonnen"
        parent.user.save(update_fields=["name", "father_name", "grandfather_name"])
        ParentStudentLinkFactory(
            student=student,
            parent=parent,
            relationship_type="MOTHER",
            is_primary_contact=True,
        )

        response = api_client.get(f"/api/students/{student.id}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["parent_details"] == [
            {
                "id": str(parent.id),
                "user": str(parent.user_id),
                "full_name": "Rahel Bekele Mekonnen",
                "relationship_type": "MOTHER",
                "is_primary_contact": True,
            },
        ]

    def test_student_list_by_academic_year_and_section_uses_year_scoped_mapping(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)
        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=None,
        )
        StudentAcademicYearSectionFactory(
            student=student,
            academic_year=section.academic_year,
            section=section,
        )

        response = api_client.get(
            f"/api/students/?academic_year={section.academic_year_id}&section={section.id}",
        )

        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data["results"]] == [str(student.id)]

    def test_student_list_supports_ordering_ascending_and_descending(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)
        StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            first_name="Bravo",
            last_name="One",
            roll_no="R103",
        )
        StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            first_name="Alpha",
            last_name="One",
            roll_no="R101",
        )
        StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            first_name="Charlie",
            last_name="One",
            roll_no="R105",
        )

        asc_response = api_client.get(
            f"/api/students/?branch={branch.id}&organization={organization.id}&ordering=roll_no",
        )
        assert asc_response.status_code == status.HTTP_200_OK
        asc_roll_nos = [item["roll_no"] for item in asc_response.data["results"]]
        assert asc_roll_nos == sorted(asc_roll_nos)

        desc_response = api_client.get(
            f"/api/students/?branch={branch.id}&organization={organization.id}&ordering=-roll_no",
        )
        assert desc_response.status_code == status.HTTP_200_OK
        desc_roll_nos = [item["roll_no"] for item in desc_response.data["results"]]
        assert desc_roll_nos == sorted(desc_roll_nos, reverse=True)

    def test_student_list_supports_ordering_with_search_and_filters(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)
        target_grade = section.grade
        match_one = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            first_name="Eden",
            roll_no="MATCH-2",
        )
        StudentAcademicYearSectionFactory(
            student=match_one,
            academic_year=section.academic_year,
            section=section,
        )
        match_two = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            first_name="Abel",
            roll_no="MATCH-1",
        )
        StudentAcademicYearSectionFactory(
            student=match_two,
            academic_year=section.academic_year,
            section=section,
        )
        other_grade = GradeFactory(organization=organization, branch=branch)
        other_section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=other_grade,
            academic_year=section.academic_year,
        )
        off_grade_match = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=other_section,
            first_name="Zulu",
            roll_no="MATCH-9",
        )
        StudentAcademicYearSectionFactory(
            student=off_grade_match,
            academic_year=section.academic_year,
            section=other_section,
        )

        response = api_client.get(
            f"/api/students/?branch={branch.id}&organization={organization.id}"
            f"&academic_year={section.academic_year_id}&grade={target_grade.id}"
            "&search=match&ordering=roll_no",
        )
        assert response.status_code == status.HTTP_200_OK

        results = response.data["results"]
        assert len(results) >= MIN_EXPECTED_MATCHED_STUDENTS
        roll_nos = [item["roll_no"] for item in results]
        assert roll_nos == sorted(roll_nos)
        assert all(item["grade_id"] == str(target_grade.id) for item in results)
        assert all("match" in item["roll_no"].lower() for item in results)

    def test_student_list_ignores_invalid_ordering_field(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)
        StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )

        response = api_client.get(
            f"/api/students/?branch={branch.id}&organization={organization.id}&ordering=not_a_field",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_parent_crud_and_custom_endpoints(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)
        parent_user = UserFactory()

        create_payload = {
            "user": str(parent_user.id),
            "organizations": [str(organization.id)],
            "branches": [str(branch.id)],
            "secondary_phone_number": "+251911000001",
            "occupation": "Engineer",
            "work_address": "HQ Building",
            "relationship_notes": "Evening pickup",
            "emergency_contact_name": "Aster",
            "emergency_contact_phone": "+251911000002",
            "is_active": True,
        }
        response = api_client.post("/api/parents/", create_payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        parent_id = response.data["id"]
        assert response.data["organization_ids"] == [str(organization.id)]
        assert response.data["branch_ids"] == [str(branch.id)]

        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        link_response = api_client.post(
            "/api/parent-links/",
            {
                "student": str(student.id),
                "parent": parent_id,
                "relationship_type": "MOTHER",
                "is_primary_contact": True,
            },
            format="json",
        )
        assert link_response.status_code == status.HTTP_201_CREATED

        response = api_client.get("/api/parents/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1
        created_parent = next(
            item for item in response.data["results"] if item["id"] == parent_id
        )
        assert created_parent["organization_ids"] == [str(organization.id)]
        assert created_parent["branch_ids"] == [str(branch.id)]

        response = api_client.get(
            f"/api/parents/?branch={branch.id}&organization={organization.id}",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"][0]["occupation"] == "Engineer"

        response = api_client.get(f"/api/parents/{parent_id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["user_details"]["email"] == parent_user.email
        assert response.data["organization_ids"] == [str(organization.id)]
        assert response.data["branch_ids"] == [str(branch.id)]

        response = api_client.patch(
            f"/api/parents/{parent_id}/",
            {"occupation": "Doctor"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["occupation"] == "Doctor"

        response = api_client.get("/api/parents/?occupation=doctor")
        assert response.status_code == status.HTTP_200_OK
        assert any(item["id"] == parent_id for item in response.data["results"])

        response = api_client.get(f"/api/parents/by-branch/?branch={branch.id}")
        assert response.status_code == status.HTTP_200_OK
        assert any(item["id"] == parent_id for item in response.data)

        response = api_client.get(
            f"/api/parents/by-organization/?organization={organization.id}",
        )
        assert response.status_code == status.HTTP_200_OK
        assert any(item["id"] == parent_id for item in response.data)

        response = api_client.get(f"/api/parents/{parent_id}/branches/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data[0]["id"] == str(branch.id)

        response = api_client.get(f"/api/parents/{parent_id}/organizations/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data[0]["id"] == str(organization.id)

        response = api_client.get(f"/api/parents/{parent_id}/students/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data[0]["id"] == str(student.id)

    def test_parent_create_accepts_alias_membership_fields(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)
        parent_user = UserFactory()

        response = api_client.post(
            "/api/parents/",
            {
                "user": str(parent_user.id),
                "organization_ids": [str(organization.id)],
                "branch_ids": [str(branch.id)],
                "secondary_phone_number": "+251911000011",
                "occupation": "Engineer",
                "work_address": "HQ Building",
                "relationship_notes": "Evening pickup",
                "emergency_contact_name": "Aster",
                "emergency_contact_phone": "+251911000012",
                "is_active": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        parent = Parent.objects.get(id=response.data["id"])
        assert list(parent.organizations.values_list("id", flat=True)) == [
            organization.id,
        ]
        assert list(parent.branches.values_list("id", flat=True)) == [branch.id]
        assert response.data["organization_ids"] == [str(organization.id)]
        assert response.data["branch_ids"] == [str(branch.id)]

    def test_parent_patch_accepts_mixed_membership_field_names(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)
        second_organization = OrganizationFactory(owner=user)
        second_branch = BranchFactory(school__organization=second_organization)
        parent = ParentFactory(
            organizations=[organization],
            branches=[branch],
        )

        response = api_client.patch(
            f"/api/parents/{parent.id}/",
            {
                "organizations": [str(organization.id), str(second_organization.id)],
                "branch_ids": [str(branch.id), str(second_branch.id)],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        parent.refresh_from_db()
        assert set(parent.organizations.values_list("id", flat=True)) == {
            organization.id,
            second_organization.id,
        }
        assert set(parent.branches.values_list("id", flat=True)) == {
            branch.id,
            second_branch.id,
        }
        assert set(response.data["organization_ids"]) == {
            str(organization.id),
            str(second_organization.id),
        }
        assert set(response.data["branch_ids"]) == {
            str(branch.id),
            str(second_branch.id),
        }

    def test_parent_create_rejects_branch_outside_selected_organizations(
        self,
        api_client,
        user,
        organization,
        branch,
    ):
        api_client.force_authenticate(user=user)
        foreign_branch = BranchFactory()
        parent_user = UserFactory()

        response = api_client.post(
            "/api/parents/",
            {
                "user": str(parent_user.id),
                "organization_ids": [str(organization.id)],
                "branch_ids": [str(branch.id), str(foreign_branch.id)],
                "is_active": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["errors"][0]["field"] == "branches"

    def test_parent_link_crud(self, api_client, user, organization, branch, section):
        api_client.force_authenticate(user=user)
        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        parent = ParentFactory(organizations=[organization], branches=[branch])

        data = {
            "student": str(student.id),
            "parent": str(parent.id),
            "relationship_type": "FATHER",
            "is_primary_contact": True,
        }
        response = api_client.post("/api/parent-links/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        link_id = response.data["id"]

        response = api_client.get("/api/parent-links/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1
        assert response.data["results"][0]["parent_details"]["id"] == str(parent.id)
        assert response.data["results"][0]["parent_details"]["organization_ids"] == [
            str(organization.id),
        ]
        assert response.data["results"][0]["parent_details"]["branch_ids"] == [
            str(branch.id),
        ]

        response = api_client.delete(f"/api/parent-links/{link_id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_parent_link_list_filters(
        self,
        api_client,
        user,
        organization,
        branch,
        section,
    ):
        api_client.force_authenticate(user=user)
        student_one = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        student_two = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        parent_one = ParentFactory(organizations=[organization], branches=[branch])
        parent_two = ParentFactory(organizations=[organization], branches=[branch])

        link_one = ParentStudentLinkFactory(
            student=student_one,
            parent=parent_one,
            relationship_type="FATHER",
            is_primary_contact=True,
        )
        link_two = ParentStudentLinkFactory(
            student=student_two,
            parent=parent_two,
            relationship_type="MOTHER",
            is_primary_contact=False,
        )

        response = api_client.get(f"/api/parent-links/?student={student_one.id}")
        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data["results"]] == [str(link_one.id)]

        response = api_client.get(f"/api/parent-links/?parent={parent_two.id}")
        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data["results"]] == [str(link_two.id)]

        response = api_client.get("/api/parent-links/?relationship_type=mother")
        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data["results"]] == [str(link_two.id)]

        response = api_client.get("/api/parent-links/?is_primary_contact=true")
        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data["results"]] == [str(link_one.id)]

    def test_student_queryset_includes_branch_admin_branch(self, user):
        organization = OrganizationFactory()
        branch = BranchFactory(school__organization=organization)
        grade = GradeFactory(organization=organization, branch=branch)
        section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
        )
        visible_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        foreign_student = StudentFactory()
        BranchAdminFactory(user=user, branch=branch)
        view = StudentViewSet()
        request = APIRequestFactory().get("/fake-url/")
        request.user = user
        request.query_params = request.GET
        view.request = request

        queryset = view.get_queryset()

        assert set(queryset) == {visible_student}
        assert foreign_student not in queryset

    def test_teacher_can_list_students_for_assigned_section(self, api_client):
        teacher_user = UserFactory(role="TEACHER")
        organization = OrganizationFactory()
        branch = BranchFactory(school__organization=organization)
        academic_year = AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            name="2025/2026",
        )
        grade = GradeFactory(organization=organization, branch=branch)
        section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
        )
        other_section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
        )
        visible_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        StudentFactory(
            organization=organization,
            branch=branch,
            current_section=other_section,
        )
        teacher = Teacher.objects.create(
            user=teacher_user,
            organization=organization,
            branch=branch,
            employee_id="EMP-STU-1",
            specialization="Mathematics",
        )
        subject = SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
        )
        TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        api_client.force_authenticate(user=teacher_user)

        response = api_client.get(f"/api/students/by-section/?section={section.id}")

        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data] == [str(visible_student.id)]

    def test_teacher_cannot_list_students_for_unassigned_section(self, api_client):
        teacher_user = UserFactory(role="TEACHER")
        organization = OrganizationFactory()
        branch = BranchFactory(school__organization=organization)
        academic_year = AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            name="2025/2026",
        )
        grade = GradeFactory(organization=organization, branch=branch)
        assigned_section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
        )
        other_section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
        )
        StudentFactory(
            organization=organization,
            branch=branch,
            current_section=other_section,
        )
        teacher = Teacher.objects.create(
            user=teacher_user,
            organization=organization,
            branch=branch,
            employee_id="EMP-STU-2",
            specialization="English",
        )
        subject = SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
        )
        TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=assigned_section,
            academic_year=academic_year,
        )
        api_client.force_authenticate(user=teacher_user)

        response = api_client.get(
            f"/api/students/by-section/?section={other_section.id}",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_teacher_can_list_student_behaviour_log(self, api_client):
        teacher_user = UserFactory(role="TEACHER", name="Ms. Hana")
        organization = OrganizationFactory()
        branch = BranchFactory(school__organization=organization)
        academic_year = AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            name="2025/2026",
        )
        grade = GradeFactory(organization=organization, branch=branch)
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
        teacher = Teacher.objects.create(
            user=teacher_user,
            organization=organization,
            branch=branch,
            employee_id="EMP-BEH-1",
            specialization="Mathematics",
        )
        subject = SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
        )
        TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        StudentBehaviourIncidentFactory(
            student=student,
            teacher=teacher_user,
            title="Late assignment submission",
            description="Submitted work after the deadline.",
            severity="MEDIUM",
            occurred_at="2026-06-01T08:00:00Z",
        )
        StudentBehaviourRemarkFactory(
            student=student,
            teacher=teacher_user,
            title="Positive participation",
            description="Participated actively in discussion.",
            severity="LOW",
            occurred_at="2026-06-02T08:00:00Z",
        )
        api_client.force_authenticate(user=teacher_user)

        response = api_client.get(f"/api/students/{student.id}/behaviour-log/")

        assert response.status_code == status.HTTP_200_OK
        assert [item["type"] for item in response.data] == ["remark", "incident"]
        assert response.data[0]["teacherName"] == "Ms. Hana"

    def test_teacher_can_create_student_behaviour_entries(self, api_client):
        teacher_user = UserFactory(role="TEACHER", name="Ms. Hana")
        organization = OrganizationFactory()
        branch = BranchFactory(school__organization=organization)
        academic_year = AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            name="2025/2026",
        )
        grade = GradeFactory(organization=organization, branch=branch)
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
        teacher = Teacher.objects.create(
            user=teacher_user,
            organization=organization,
            branch=branch,
            employee_id="EMP-BEH-2",
            specialization="Mathematics",
        )
        subject = SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
        )
        TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        api_client.force_authenticate(user=teacher_user)

        incident_response = api_client.post(
            f"/api/students/{student.id}/behaviour-log/",
            {
                "type": "incident",
                "title": "Late assignment submission",
                "description": "Work arrived after the deadline.",
                "severity": "HIGH",
            },
            format="json",
        )
        remark_response = api_client.post(
            f"/api/students/{student.id}/behaviour-log/",
            {
                "type": "remark",
                "title": "Participation",
                "description": "Asked thoughtful questions.",
            },
            format="json",
        )

        assert incident_response.status_code == status.HTTP_201_CREATED
        assert incident_response.data["type"] == "incident"
        assert incident_response.data["severity"] == "HIGH"
        assert incident_response.data["teacherName"] == "Ms. Hana"
        assert remark_response.status_code == status.HTTP_201_CREATED
        assert remark_response.data["type"] == "remark"
        assert remark_response.data["severity"] == "LOW"

    def test_homeroom_teacher_can_list_students_for_assigned_section(self, api_client):
        teacher_user = UserFactory(role="TEACHER")
        organization = OrganizationFactory()
        branch = BranchFactory(school__organization=organization)
        academic_year = AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            name="2025/2026",
        )
        grade = GradeFactory(organization=organization, branch=branch)
        section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
        )
        visible_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        teacher = Teacher.objects.create(
            user=teacher_user,
            organization=organization,
            branch=branch,
            employee_id="EMP-STU-3",
            specialization="Homeroom",
        )
        HomeroomAssignment.objects.create(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            teacher=teacher,
        )
        api_client.force_authenticate(user=teacher_user)

        response = api_client.get(f"/api/students/by-section/?section={section.id}")

        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data] == [str(visible_student.id)]

    def test_teacher_can_list_parents_and_links_for_assigned_section(self, api_client):
        teacher_user = UserFactory(role="TEACHER")
        organization = OrganizationFactory()
        branch = BranchFactory(school__organization=organization)
        academic_year = AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            name="2025/2026",
        )
        grade = GradeFactory(organization=organization, branch=branch)
        section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
        )
        other_section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
        )
        visible_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        hidden_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=other_section,
        )
        visible_parent = ParentFactory(organizations=[organization], branches=[branch])
        hidden_parent = ParentFactory(organizations=[organization], branches=[branch])
        visible_link = ParentStudentLinkFactory(
            student=visible_student,
            parent=visible_parent,
        )
        ParentStudentLinkFactory(
            student=hidden_student,
            parent=hidden_parent,
        )
        teacher = Teacher.objects.create(
            user=teacher_user,
            organization=organization,
            branch=branch,
            employee_id="TCHPARENT001",
            specialization="Science",
        )
        subject = SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
        )
        TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        api_client.force_authenticate(user=teacher_user)

        parents_response = api_client.get("/api/parents/")
        assert parents_response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in parents_response.data["results"]] == [
            str(visible_parent.id),
        ]

        links_response = api_client.get("/api/parent-links/")
        assert links_response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in links_response.data["results"]] == [
            str(visible_link.id),
        ]

    def test_parent_queryset_includes_branch_admin_branch(self, user):
        organization = OrganizationFactory()
        branch = BranchFactory(school__organization=organization)
        visible_parent = ParentFactory(organizations=[organization], branches=[branch])
        foreign_parent = ParentFactory()
        BranchAdminFactory(user=user, branch=branch, organization=organization)
        view = ParentViewSet()
        request = APIRequestFactory().get("/fake-url/")
        request.user = user
        request.query_params = request.GET
        view.request = request

        queryset = view.get_queryset()

        assert set(queryset) == {visible_parent}
        assert foreign_parent not in queryset

    def test_parent_me_and_my_students(self, api_client, organization, branch, section):
        parent_user = UserFactory(role="PARENT")
        parent = ParentFactory(
            user=parent_user,
            organizations=[organization],
            branches=[branch],
        )
        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        ParentStudentLinkFactory(student=student, parent=parent)
        api_client.force_authenticate(user=parent_user)

        response = api_client.get("/api/parents/me/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(parent.id)

        response = api_client.get("/api/parents/my-students/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data[0]["id"] == str(student.id)
        assert response.data[0]["grade_id"] == str(section.grade_id)

    def test_parent_my_student_behaviour_log_merges_incidents_and_remarks(
        self,
        api_client,
        organization,
        branch,
        section,
    ):
        parent_user = UserFactory(role="PARENT")
        parent = ParentFactory(
            user=parent_user,
            organizations=[organization],
            branches=[branch],
        )
        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        ParentStudentLinkFactory(student=student, parent=parent)
        teacher = UserFactory(role="TEACHER", name="Ms. Hana")
        older_incident = StudentBehaviourIncidentFactory(
            student=student,
            teacher=teacher,
            title="Classroom disruption",
            description="Interrupted classmates during group work.",
            severity="HIGH",
            occurred_at="2026-06-01T08:00:00Z",
        )
        newer_remark = StudentBehaviourRemarkFactory(
            student=student,
            teacher=teacher,
            title="Improved focus",
            description="Stayed focused throughout the lesson.",
            severity="LOW",
            occurred_at="2026-06-02T08:00:00Z",
        )
        api_client.force_authenticate(user=parent_user)

        response = api_client.get(
            f"/api/parents/my-students/{student.id}/behaviour-log/",
        )

        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data] == [
            str(newer_remark.id),
            str(older_incident.id),
        ]
        assert response.data[0]["type"] == "remark"
        assert response.data[0]["teacherName"] == "Ms. Hana"
        assert response.data[1]["type"] == "incident"
        assert response.data[1]["severity"] == "HIGH"

    def test_parent_my_student_behaviour_log_rejects_unlinked_student(
        self,
        api_client,
        organization,
        branch,
        section,
    ):
        parent_user = UserFactory(role="PARENT")
        parent = ParentFactory(
            user=parent_user,
            organizations=[organization],
            branches=[branch],
        )
        linked_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        ParentStudentLinkFactory(student=linked_student, parent=parent)
        other_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        StudentBehaviourIncidentFactory(student=other_student)
        api_client.force_authenticate(user=parent_user)

        response = api_client.get(
            f"/api/parents/my-students/{other_student.id}/behaviour-log/",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_student_schema_lists_manual_filters(self, api_client):
        api_client.force_authenticate(
            user=UserFactory(is_staff=True, is_superuser=True),
        )

        response = api_client.get("/api/schema/")

        assert response.status_code == status.HTTP_200_OK
        parameters = response.data["paths"]["/api/students/"]["get"]["parameters"]
        parameter_names = {parameter["name"] for parameter in parameters}

        assert {
            "section",
            "grade",
            "branch",
            "organization",
            "academic_year",
            "status",
            "gender",
            "ordering",
        }.issubset(parameter_names)

    def test_parent_schema_lists_manual_filters(self, api_client):
        api_client.force_authenticate(
            user=UserFactory(is_staff=True, is_superuser=True),
        )

        response = api_client.get("/api/schema/")

        assert response.status_code == status.HTTP_200_OK
        parameters = response.data["paths"]["/api/parents/"]["get"]["parameters"]
        parameter_names = {parameter["name"] for parameter in parameters}

        assert {
            "organization",
            "branch",
            "user",
            "occupation",
            "is_active",
        }.issubset(parameter_names)


@pytest.mark.django_db
class TestStudentInsightDemoTriggerAPI:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    def _build_teacher_with_assignment(
        self,
        *,
        organization,
        branch,
        section,
    ):
        teacher = Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Assigned Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-DEMO-1",
            specialization="Mathematics",
        )
        subject = SubjectFactory(
            organization=organization,
            branch=branch,
            grade=section.grade,
            name="Mathematics",
        )
        TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=section.academic_year,
        )
        return teacher

    def test_assigned_teacher_can_trigger_student_insight_demo(
        self,
        api_client,
        organization,
        branch,
        section,
    ):
        teacher = self._build_teacher_with_assignment(
            organization=organization,
            branch=branch,
            section=section,
        )
        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        ParentStudentLinkFactory(
            student=student,
            parent=ParentFactory(
                organizations=[organization],
                branches=[branch],
            ),
        )
        assessment = SubjectFactory(
            organization=organization,
            branch=branch,
            grade=section.grade,
            name="Algebra",
        )
        assignment = TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=assessment,
            section=section,
            academic_year=section.academic_year,
        )
        result = AssessmentResult.objects.create(
            organization=organization,
            assessment=Assessment.objects.create(
                organization=organization,
                branch=branch,
                teacher_assignment=assignment,
                title="Demo Quiz",
                task_type=Assessment.TaskType.QUIZ,
                description="Demo",
                total_marks="100",
                passing_marks="50",
                status=Assessment.Status.PUBLISHED,
            ),
            student=student,
            obtained_marks="30",
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
        )
        del result

        api_client.force_authenticate(user=teacher.user)

        response = api_client.post(
            f"/api/students/{student.id}/trigger-insight-demo/",
            {},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["created"] is True
        assert response.data["category"] == StudentInsight.Category.ACADEMICS

    def test_unassigned_teacher_cannot_trigger_student_insight_demo(
        self,
        api_client,
        organization,
        branch,
        section,
    ):
        teacher = Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Unassigned Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-DEMO-2",
            specialization="English",
        )
        student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )

        api_client.force_authenticate(user=teacher.user)

        response = api_client.post(
            f"/api/students/{student.id}/trigger-insight-demo/",
            {},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

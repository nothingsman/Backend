import pytest
from rest_framework import status
from rest_framework.test import APIClient
from student_insights.models import StudentInsight
from students.tests.factories import ParentFactory
from students.tests.factories import ParentStudentLinkFactory
from students.tests.factories import StudentFactory


@pytest.mark.django_db
class TestStudentInsightAPI:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    def test_parent_can_only_fetch_linked_student_insights(self, api_client):
        linked_student = StudentFactory()
        other_student = StudentFactory()
        parent = ParentFactory(
            organizations=[linked_student.organization],
            branches=[linked_student.branch],
        )
        ParentStudentLinkFactory(student=linked_student, parent=parent)

        linked = StudentInsight.objects.create(
            organization=linked_student.organization,
            branch=linked_student.branch,
            student=linked_student,
            source_event_type=StudentInsight.SourceEventType.ATTENDANCE,
            source_model="attendance.Attendance",
            source_id=None,
            dedupe_key="attendance:linked",
            category=StudentInsight.Category.ATTENDANCE,
            risk_band=StudentInsight.RiskBand.LOW,
            title="Linked insight",
            message="Visible to linked parent",
            confidence_label="RULE_BASED",
        )
        StudentInsight.objects.create(
            organization=other_student.organization,
            branch=other_student.branch,
            student=other_student,
            source_event_type=StudentInsight.SourceEventType.ATTENDANCE,
            source_model="attendance.Attendance",
            source_id=None,
            dedupe_key="attendance:other",
            category=StudentInsight.Category.ATTENDANCE,
            risk_band=StudentInsight.RiskBand.LOW,
            title="Other insight",
            message="Should not be visible",
            confidence_label="RULE_BASED",
        )

        api_client.force_authenticate(user=parent.user)

        list_response = api_client.get("/api/student-insights/")
        detail_response = api_client.get(f"/api/student-insights/{linked.id}/")

        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["count"] == 1
        assert list_response.data["results"][0]["id"] == str(linked.id)
        assert detail_response.status_code == status.HTTP_200_OK
        assert detail_response.data["id"] == str(linked.id)

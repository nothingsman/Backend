from django.db.models import Q
from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet
from student_insights.api.serializers import StudentInsightSerializer
from student_insights.models import StudentInsight


class StudentInsightViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    serializer_class = StudentInsightSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        queryset = StudentInsight.objects.select_related("student")
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()

        user = self.request.user
        if user.is_superuser:
            return queryset

        parent_filter = Q(student__parent_links__parent__user=user)
        queryset = queryset.filter(parent_filter).distinct()

        student_id = self.request.query_params.get("student")
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        return queryset

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from academics.models import AcademicYear
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from accounts.tests.factories import UserFactory
from branches.tests.factories import BranchFactory
from organizations.tests.factories import OrganizationFactory

if TYPE_CHECKING:
    from academics.models import Section
    from accounts.models import User
    from branches.models import Branch
    from organizations.models import Organization


@pytest.fixture
def user() -> User:
    return UserFactory()


@pytest.fixture
def organization(user) -> Organization:
    return OrganizationFactory(owner=user)


@pytest.fixture
def branch(organization) -> Branch:
    return BranchFactory(school__organization=organization)


@pytest.fixture
def section(organization, branch) -> Section:
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

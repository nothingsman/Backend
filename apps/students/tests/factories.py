import factory
from academics.tests.factories import AcademicYearFactory
from academics.tests.factories import SectionFactory
from accounts.tests.factories import UserFactory
from branches.tests.factories import BranchFactory
from factory.django import DjangoModelFactory
from organizations.tests.factories import OrganizationFactory
from students.models import Parent
from students.models import ParentStudentLink
from students.models import Student
from students.models import StudentAcademicYearSection
from students.models import StudentBehaviourIncident
from students.models import StudentBehaviourRemark


class StudentFactory(DjangoModelFactory):
    organization = factory.SubFactory(OrganizationFactory)
    branch = factory.SubFactory(BranchFactory)
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    gender = factory.Iterator(["MALE", "FEMALE"])
    date_of_birth = factory.Faker("date_of_birth", minimum_age=5, maximum_age=18)
    roll_no = factory.Sequence(lambda n: f"STU{n:04d}")
    current_section = factory.SubFactory(SectionFactory)
    admission_date = factory.Faker("date_this_decade")
    status = "ACTIVE"

    class Meta:
        model = Student


class ParentFactory(DjangoModelFactory):
    user = factory.SubFactory(UserFactory, role="PARENT")
    secondary_phone_number = factory.Faker("numerify", text="##########")
    occupation = factory.Faker("job")
    work_address = factory.Faker("address")
    relationship_notes = ""
    emergency_contact_name = factory.Faker("name")
    emergency_contact_phone = factory.Faker("numerify", text="##########")
    is_active = True

    class Meta:
        model = Parent

    @factory.post_generation
    def organizations(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.organizations.set(extracted)
            return
        organization = OrganizationFactory(owner=self.user)
        self.organizations.add(organization)

    @factory.post_generation
    def branches(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.branches.set(extracted)
            return
        organization = self.organizations.first()
        self.branches.add(BranchFactory(school__organization=organization))


class ParentStudentLinkFactory(DjangoModelFactory):
    student = factory.SubFactory(StudentFactory)
    parent = factory.SubFactory(ParentFactory)
    relationship_type = factory.Iterator(["FATHER", "MOTHER", "GUARDIAN"])
    is_primary_contact = False

    class Meta:
        model = ParentStudentLink

    @factory.post_generation
    def align_parent_membership(self, create, extracted, **kwargs):
        if not create:
            return
        self.parent.organizations.add(self.student.organization)
        self.parent.branches.add(self.student.branch)


class StudentAcademicYearSectionFactory(DjangoModelFactory):
    student = factory.SubFactory(StudentFactory)
    academic_year = factory.SubFactory(AcademicYearFactory)
    section = None

    class Meta:
        model = StudentAcademicYearSection


class StudentBehaviourIncidentFactory(DjangoModelFactory):
    student = factory.SubFactory(StudentFactory)
    teacher = factory.SubFactory(UserFactory, role="TEACHER")
    title = factory.Sequence(lambda n: f"Incident {n + 1}")
    description = factory.Faker("sentence")
    severity = "MEDIUM"
    occurred_at = factory.Faker("date_time_this_year")
    source = "Teacher Incident"

    class Meta:
        model = StudentBehaviourIncident


class StudentBehaviourRemarkFactory(DjangoModelFactory):
    student = factory.SubFactory(StudentFactory)
    teacher = factory.SubFactory(UserFactory, role="TEACHER")
    title = factory.Sequence(lambda n: f"Remark {n + 1}")
    description = factory.Faker("sentence")
    severity = "LOW"
    occurred_at = factory.Faker("date_time_this_year")
    source = "Teacher Remark"

    class Meta:
        model = StudentBehaviourRemark

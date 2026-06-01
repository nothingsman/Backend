import io
import uuid
from typing import Any

import pandas as pd
from academics.models import AcademicYear
from academics.models import Section
from accounts.models import User
from branches.models import Branch
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import DatabaseError
from django.db import transaction
from django.utils import timezone
from organizations.models import Organization
from students.models import Parent
from students.models import ParentStudentLink
from students.models import Student
from students.models import StudentAcademicYearSection

FILE_PARSE_EXCEPTIONS = (
    pd.errors.EmptyDataError,
    pd.errors.ParserError,
    UnicodeDecodeError,
    ValueError,
)
DATE_PARSE_EXCEPTIONS = (TypeError, ValueError)
BRANCH_NOT_FOUND_MESSAGE = "Branch not found or does not belong to organization."


class _BulkImportServiceBase:
    def __init__(
        self,
        file_content,
        file_name,
        organization_id,
        branch_id,
        current_section=None,
    ):
        self.file_content = file_content
        self.file_name = file_name
        self.organization_id = organization_id
        self.branch_id = branch_id
        self.current_section = current_section
        self.errors: list[dict[str, Any]] = []

    def _parse_dataframe(
        self,
        required_columns: list[str],
    ) -> tuple[pd.DataFrame | None, list[dict[str, Any]]]:
        try:
            if self.file_name.endswith(".csv"):
                data = io.StringIO(self.file_content.decode("utf-8"))
                dataframe = pd.read_csv(data, dtype=str, keep_default_na=False)
            elif self.file_name.endswith((".xls", ".xlsx")):
                data = io.BytesIO(self.file_content)
                dataframe = pd.read_excel(data, dtype=str, keep_default_na=False)
            else:
                return None, [self._error(0, "file", self._unsupported_file_message())]
        except FILE_PARSE_EXCEPTIONS as exc:
            return None, [self._error(0, "file", f"Failed to parse file: {exc!s}")]

        dataframe.columns = [
            str(column).strip().lower() for column in dataframe.columns
        ]

        missing_columns = [
            column for column in required_columns if column not in dataframe.columns
        ]
        if missing_columns:
            return None, [
                self._error(
                    0,
                    "columns",
                    f"Missing required columns: {', '.join(missing_columns)}",
                ),
            ]

        return dataframe.fillna(""), []

    def _get_context(
        self,
    ) -> tuple[Organization | None, Branch | None, list[dict[str, Any]]]:
        try:
            organization = Organization.objects.get(id=self.organization_id)
        except Organization.DoesNotExist:
            return (
                None,
                None,
                [
                    self._error(0, "organization", "Organization not found."),
                ],
            )

        try:
            branch = Branch.objects.get(id=self.branch_id, organization=organization)
        except Branch.DoesNotExist:
            return None, None, [self._error(0, "branch", BRANCH_NOT_FOUND_MESSAGE)]

        return organization, branch, []

    @staticmethod
    def _text_value(row: pd.Series, key: str) -> str:
        value = row.get(key)
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _unsupported_file_message() -> str:
        return "Unsupported file format. Please upload CSV or Excel."

    @staticmethod
    def _error(row: int, field: str, message: str) -> dict[str, Any]:
        return {"row": row, "errors": {field: [message]}}


class ParentBulkImportService(_BulkImportServiceBase):
    def run(self) -> tuple[bool, list[dict[str, Any]]]:
        dataframe, parse_errors = self._parse_dataframe(
            ["name", "father_name", "grandfather_name", "phone_number"],
        )
        if parse_errors:
            return False, parse_errors

        org, branch, context_errors = self._get_context()
        if context_errors:
            return False, context_errors

        prepared_rows = self._validate_rows(dataframe)
        if self.errors:
            return False, self.errors

        self._create_or_update_parents(prepared_rows, org, branch)
        if self.errors:
            return False, self.errors

        return True, []

    def _validate_rows(self, dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        prepared_rows: list[dict[str, Any]] = []
        seen_emails: set[str] = set()
        seen_phones: set[str] = set()

        for index, row in dataframe.iterrows():
            row_number = index + 2
            row_errors: dict[str, list[str]] = {}
            prepared_row = self._build_row_payload(
                row=row,
                row_errors=row_errors,
                seen_emails=seen_emails,
                seen_phones=seen_phones,
            )

            if row_errors:
                self.errors.append({"row": row_number, "errors": row_errors})
                continue

            prepared_rows.append(prepared_row)

        return prepared_rows

    def _build_row_payload(
        self,
        *,
        row: pd.Series,
        row_errors: dict[str, list[str]],
        seen_emails: set[str],
        seen_phones: set[str],
    ) -> dict[str, Any]:
        name = self._text_value(row, "name")
        email = self._text_value(row, "email")
        phone_number = self._text_value(row, "phone_number")
        father_name = self._text_value(row, "father_name")
        grandfather_name = self._text_value(row, "grandfather_name")

        if not name:
            row_errors["name"] = ["Name is required."]
        if not father_name:
            row_errors["father_name"] = ["Father name is required."]
        if not grandfather_name:
            row_errors["grandfather_name"] = ["Grandfather name is required."]

        self._validate_parent_email(email, row_errors, seen_emails)
        self._validate_parent_phone(phone_number, row_errors, seen_phones)

        existing_user = User.objects.filter(phone_number=phone_number).first()
        self._validate_existing_parent_user(existing_user, email, row_errors)

        return {
            "name": name,
            "email": email,
            "phone_number": phone_number,
            "father_name": father_name,
            "grandfather_name": grandfather_name,
            "secondary_phone_number": self._text_value(row, "secondary_phone_number"),
            "occupation": self._text_value(row, "occupation"),
            "work_address": self._text_value(row, "work_address"),
            "emergency_contact_name": self._text_value(
                row,
                "emergency_contact_name",
            ),
            "emergency_contact_phone": self._text_value(
                row,
                "emergency_contact_phone",
            ),
            "existing_user": existing_user,
        }

    def _validate_parent_email(
        self,
        email: str,
        row_errors: dict[str, list[str]],
        seen_emails: set[str],
    ) -> None:
        if not email:
            return

        try:
            validate_email(email)
        except ValidationError:
            row_errors["email"] = ["Invalid email format."]
            return

        normalized_email = email.lower()
        if normalized_email in seen_emails:
            row_errors["email"] = ["Duplicate email in the sheet."]
            return

        seen_emails.add(normalized_email)

    def _validate_parent_phone(
        self,
        phone_number: str,
        row_errors: dict[str, list[str]],
        seen_phones: set[str],
    ) -> None:
        if not phone_number:
            row_errors["phone_number"] = ["Phone number is required."]
            return

        if phone_number in seen_phones:
            row_errors["phone_number"] = ["Duplicate phone number in the sheet."]
            return

        seen_phones.add(phone_number)

    def _validate_existing_parent_user(
        self,
        existing_user: User | None,
        email: str,
        row_errors: dict[str, list[str]],
    ) -> None:
        if existing_user is None:
            if email and User.objects.filter(email__iexact=email).exists():
                row_errors["email"] = [
                    "This email is already registered to another user.",
                ]
            return

        if existing_user.role != User.Role.PARENT:
            row_errors["phone_number"] = [
                (
                    "A user with this phone number exists but is not a Parent "
                    f"(role: {existing_user.role})."
                ),
            ]
            return

        if email and existing_user.email != email:
            email_in_use = (
                User.objects.exclude(id=existing_user.id)
                .filter(email__iexact=email)
                .exists()
            )
            if email_in_use:
                row_errors["email"] = [
                    "This email is already registered to another user.",
                ]

    def _create_or_update_parents(
        self,
        prepared_rows: list[dict[str, Any]],
        organization: Organization,
        branch: Branch,
    ) -> None:
        try:
            with transaction.atomic():
                for row_data in prepared_rows:
                    parent_profile = self._save_parent(row_data)
                    parent_profile.organizations.add(organization)
                    parent_profile.branches.add(branch)
                    self._update_parent_profile(parent_profile, row_data)
                    parent_profile.save()
        except DatabaseError as exc:
            self.errors.append(self._error(0, "server", f"Internal error: {exc!s}"))

    def _save_parent(self, row_data: dict[str, Any]) -> Parent:
        existing_user = row_data["existing_user"]
        email = row_data["email"] or None

        if existing_user is None:
            user = User.objects.create_user(
                email=email,
                name=row_data["name"],
                father_name=row_data["father_name"],
                grandfather_name=row_data["grandfather_name"],
                phone_number=row_data["phone_number"],
                role=User.Role.PARENT,
                is_active=False,
            )
            user.set_unusable_password()
            user.save(update_fields=["password"])
            return Parent.objects.create(user=user, is_active=False)

        if email and existing_user.email != email:
            existing_user.email = email
        existing_user.is_active = False
        existing_user.verified_at = None
        existing_user.save(update_fields=["email", "is_active", "verified_at"])

        parent_profile, _ = Parent.objects.get_or_create(user=existing_user)
        parent_profile.is_active = False
        return parent_profile

    @staticmethod
    def _update_parent_profile(
        parent_profile: Parent,
        row_data: dict[str, Any],
    ) -> None:
        optional_fields = [
            "secondary_phone_number",
            "occupation",
            "work_address",
            "emergency_contact_name",
            "emergency_contact_phone",
        ]
        for field_name in optional_fields:
            value = row_data[field_name]
            if value:
                setattr(parent_profile, field_name, value)


class StudentBulkImportService(_BulkImportServiceBase):
    def run(self) -> tuple[bool, list[dict[str, Any]]]:
        dataframe, parse_errors = self._parse_dataframe(
            ["first_name", "last_name", "gender", "date_of_birth"],
        )
        if parse_errors:
            return False, parse_errors

        org, branch, context_errors = self._get_context()
        if context_errors:
            return False, context_errors

        prepared_rows = self._validate_rows(dataframe, branch)
        if self.errors:
            return False, self.errors

        self._create_students(prepared_rows, org, branch)
        if self.errors:
            return False, self.errors

        return True, []

    def _validate_rows(
        self,
        dataframe: pd.DataFrame,
        branch: Branch,
    ) -> list[dict[str, Any]]:
        prepared_rows: list[dict[str, Any]] = []
        seen_roll_numbers: set[tuple[int | None, str]] = set()
        current_academic_year = AcademicYear.objects.filter(
            branch=branch,
            organization_id=self.organization_id,
            is_current=True,
        ).first()

        for index, row in dataframe.iterrows():
            row_number = index + 2
            row_errors: dict[str, list[str]] = {}
            prepared_row = self._build_row_payload(
                row=row,
                branch=branch,
                current_academic_year=current_academic_year,
                row_errors=row_errors,
                seen_roll_numbers=seen_roll_numbers,
            )

            if row_errors:
                if "parent_emails" in row_errors:
                    row_errors["parent_emails"] = [
                        "; ".join(row_errors["parent_emails"]),
                    ]
                self.errors.append({"row": row_number, "errors": row_errors})
                continue

            prepared_rows.append(prepared_row)

        return prepared_rows

    def _build_row_payload(
        self,
        *,
        row: pd.Series,
        branch: Branch,
        current_academic_year: AcademicYear | None,
        row_errors: dict[str, list[str]],
        seen_roll_numbers: set[tuple[int | None, str]],
    ) -> dict[str, Any]:
        first_name = self._text_value(row, "first_name")
        last_name = self._text_value(row, "last_name")
        gender = self._text_value(row, "gender").upper()
        grade_name = self._text_value(row, "grade_name") or None
        section_name = self._text_value(row, "section_name")
        roll_no = self._text_value(row, "roll_no") or self._generate_roll_number()

        self._validate_student_identity(first_name, last_name, gender, row_errors)
        date_of_birth = self._resolve_required_date(
            row.get("date_of_birth"),
            "date_of_birth",
            row_errors,
        )
        admission_date = self._resolve_admission_date(
            row.get("admission_date"),
            row_errors,
        )
        override_section = self.current_section
        section = (
            override_section
            if override_section is not None
            else self._resolve_section(
                branch=branch,
                section_name=section_name,
                grade_name=grade_name,
                row_errors=row_errors,
            )
        )
        academic_year = (
            override_section.academic_year
            if override_section is not None
            else self._resolve_academic_year(
                section=section,
                current_academic_year=current_academic_year,
                row_errors=row_errors,
            )
        )
        self._validate_roll_number(
            roll_no=roll_no,
            section=section,
            branch=branch,
            row_errors=row_errors,
            seen_roll_numbers=seen_roll_numbers,
        )
        parent_links = self._build_parent_links(
            row=row,
            row_errors=row_errors,
        )

        return {
            "first_name": first_name,
            "last_name": last_name,
            "gender": gender,
            "date_of_birth": date_of_birth,
            "roll_no": roll_no,
            "academic_year": academic_year,
            "current_section": section,
            "admission_date": admission_date,
            "parent_links": parent_links,
        }

    def _validate_student_identity(
        self,
        first_name: str,
        last_name: str,
        gender: str,
        row_errors: dict[str, list[str]],
    ) -> None:
        if not first_name:
            row_errors["first_name"] = ["First name is required."]
        if not last_name:
            row_errors["last_name"] = ["Last name is required."]
        if gender not in dict(Student.Gender.choices):
            row_errors["gender"] = [
                "Invalid gender. Must be one of: "
                f"{', '.join(dict(Student.Gender.choices).keys())}.",
            ]

    def _resolve_required_date(
        self,
        raw_value: Any,
        field_name: str,
        row_errors: dict[str, list[str]],
    ):
        try:
            return pd.to_datetime(raw_value).date()
        except DATE_PARSE_EXCEPTIONS:
            row_errors[field_name] = ["Invalid date format. Use YYYY-MM-DD."]
            return None

    def _resolve_admission_date(
        self,
        raw_value: Any,
        row_errors: dict[str, list[str]],
    ):
        if raw_value is None or str(raw_value).strip() == "":
            return timezone.now().date()

        try:
            return pd.to_datetime(raw_value).date()
        except DATE_PARSE_EXCEPTIONS:
            row_errors["admission_date"] = ["Invalid date format. Use YYYY-MM-DD."]
            return None

    def _resolve_section(
        self,
        *,
        branch: Branch,
        section_name: str,
        grade_name: str | None,
        row_errors: dict[str, list[str]],
    ) -> Section | None:
        if not section_name:
            return None

        sections = Section.objects.filter(branch=branch, name__iexact=section_name)
        if grade_name:
            sections = sections.filter(grade__name__iexact=grade_name)

        count = sections.count()
        if count == 0:
            error_message = f"Section '{section_name}' not found"
            if grade_name:
                error_message += f" for Grade '{grade_name}'"
            row_errors["section_name"] = [f"{error_message}."]
            return None

        if count > 1:
            if grade_name is None:
                return None
            row_errors["section_name"] = [
                (
                    f"Multiple sections found named '{section_name}'. Please "
                    "specify 'grade_name' to disambiguate."
                ),
            ]
            return None

        return sections.first()

    @staticmethod
    def _resolve_academic_year(
        *,
        section: Section | None,
        current_academic_year: AcademicYear | None,
        row_errors: dict[str, list[str]],
    ) -> AcademicYear | None:
        if section is not None:
            if section.academic_year is None:
                row_errors["section_name"] = [
                    "Selected section must belong to an academic year.",
                ]
                return None
            return section.academic_year

        if current_academic_year is None:
            row_errors["academic_year"] = [
                "Current academic year not found for the selected branch.",
            ]
            return None

        return current_academic_year

    def _validate_roll_number(
        self,
        *,
        roll_no: str,
        section: Section | None,
        branch: Branch,
        row_errors: dict[str, list[str]],
        seen_roll_numbers: set[tuple[int | None, str]],
    ) -> None:
        roll_key = (section.id if section else None, roll_no.lower())
        if roll_key in seen_roll_numbers:
            row_errors["roll_no"] = [
                "Duplicate roll number in this section within the sheet.",
            ]
            return

        seen_roll_numbers.add(roll_key)
        if (
            section
            and Student.objects.filter(
                branch=branch,
                current_section=section,
                roll_no__iexact=roll_no,
            ).exists()
        ):
            row_errors["roll_no"] = ["Roll number already exists in this section."]

    def _build_parent_links(
        self,
        *,
        row: pd.Series,
        row_errors: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        parent_emails_raw = self._text_value(row, "parent_emails")
        if not parent_emails_raw:
            return []

        emails = [
            email.strip() for email in parent_emails_raw.split(",") if email.strip()
        ]
        relationships = [
            relation.strip().upper()
            for relation in self._text_value(row, "relationship_types").split(",")
            if relation.strip()
        ]
        primary_flags = [
            flag.strip().lower() in ("true", "1", "yes")
            for flag in self._text_value(row, "is_primary_contacts").split(",")
            if flag.strip()
        ]

        parent_links: list[dict[str, Any]] = []
        for index, email in enumerate(emails):
            parent_profile = self._resolve_parent_profile(email, row_errors)
            if parent_profile is None:
                continue

            relationship_type = self._resolve_relationship_type(relationships, index)
            is_primary_contact = (
                primary_flags[index] if index < len(primary_flags) else False
            )
            parent_links.append(
                {
                    "parent": parent_profile,
                    "relationship_type": relationship_type,
                    "is_primary_contact": is_primary_contact,
                },
            )

        return parent_links

    def _resolve_parent_profile(
        self,
        email: str,
        row_errors: dict[str, list[str]],
    ) -> Parent | None:
        try:
            validate_email(email)
        except ValidationError:
            self._append_parent_email_error(row_errors, f"Invalid email: {email}")
            return None

        parent_profile = Parent.objects.filter(user__email__iexact=email).first()
        if parent_profile is None:
            self._append_parent_email_error(
                row_errors,
                f"Parent with email '{email}' not found. Please import parents first.",
            )
            return None

        belongs_to_context = (
            parent_profile.organizations.filter(id=self.organization_id).exists()
            and parent_profile.branches.filter(id=self.branch_id).exists()
        )
        if not belongs_to_context:
            self._append_parent_email_error(
                row_errors,
                (
                    f"Parent '{email}' exists but is not linked to this "
                    "organization/branch."
                ),
            )
            return None

        return parent_profile

    @staticmethod
    def _resolve_relationship_type(relationships: list[str], index: int) -> str:
        relationship_type = (
            relationships[index] if index < len(relationships) else "GUARDIAN"
        )
        if relationship_type not in dict(ParentStudentLink.Relationship.choices):
            return "OTHER"
        return relationship_type

    @staticmethod
    def _append_parent_email_error(
        row_errors: dict[str, list[str]],
        message: str,
    ) -> None:
        row_errors.setdefault("parent_emails", []).append(message)

    @staticmethod
    def _generate_roll_number() -> str:
        return f"STU-{uuid.uuid4().hex[:8].upper()}"

    def _create_students(
        self,
        prepared_rows: list[dict[str, Any]],
        organization: Organization,
        branch: Branch,
    ) -> None:
        try:
            with transaction.atomic():
                for row_data in prepared_rows:
                    student = Student.objects.create(
                        organization=organization,
                        branch=branch,
                        first_name=row_data["first_name"],
                        last_name=row_data["last_name"],
                        gender=row_data["gender"],
                        date_of_birth=row_data["date_of_birth"],
                        roll_no=row_data["roll_no"],
                        current_section=(
                            row_data["current_section"]
                            if row_data["academic_year"].is_current
                            else None
                        ),
                        admission_date=row_data["admission_date"],
                    )
                    assignment = StudentAcademicYearSection(
                        student=student,
                        academic_year=row_data["academic_year"],
                        section=row_data["current_section"],
                    )
                    assignment.full_clean()
                    assignment.save()
                    self._create_parent_links(student, row_data["parent_links"])
        except DatabaseError as exc:
            self.errors.append(self._error(0, "server", f"Internal error: {exc!s}"))

    @staticmethod
    def _create_parent_links(
        student: Student,
        parent_links: list[dict[str, Any]],
    ) -> None:
        for link_data in parent_links:
            ParentStudentLink.objects.create(
                student=student,
                parent=link_data["parent"],
                relationship_type=link_data["relationship_type"],
                is_primary_contact=link_data["is_primary_contact"],
            )

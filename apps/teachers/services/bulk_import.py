import io
import uuid
from typing import Any

import pandas as pd
from accounts.models import User
from branches.models import Branch
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import DatabaseError
from django.db import transaction
from django.utils import timezone
from organizations.models import Organization
from teachers.models import Teacher

FILE_PARSE_EXCEPTIONS = (
    pd.errors.EmptyDataError,
    pd.errors.ParserError,
    UnicodeDecodeError,
    ValueError,
)
DATE_PARSE_EXCEPTIONS = (TypeError, ValueError)
BRANCH_NOT_FOUND_MESSAGE = "Branch not found or does not belong to organization."


class TeacherBulkImportService:
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

    def run(self) -> tuple[bool, list[dict[str, Any]]]:
        dataframe, parse_errors = self._parse_dataframe()
        if parse_errors:
            return False, parse_errors

        org, branch, context_errors = self._get_context()
        if context_errors:
            return False, context_errors

        prepared_rows = self._validate_rows(dataframe, branch)
        if self.errors:
            return False, self.errors

        self._create_teachers(prepared_rows, org, branch)
        if self.errors:
            return False, self.errors

        return True, []

    def _parse_dataframe(self) -> tuple[pd.DataFrame | None, list[dict[str, Any]]]:
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

        required_columns = [
            "name",
            "father_name",
            "grandfather_name",
            "email",
            "phone_number",
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

    def _validate_rows(
        self,
        dataframe: pd.DataFrame,
        branch: Branch,
    ) -> list[dict[str, Any]]:
        prepared_rows: list[dict[str, Any]] = []
        seen_emails: set[str] = set()
        seen_employee_ids: set[str] = set()

        for index, row in dataframe.iterrows():
            row_number = index + 2
            row_errors: dict[str, list[str]] = {}
            prepared_row = self._build_row_payload(
                row=row,
                branch=branch,
                seen_values={
                    "emails": seen_emails,
                    "employee_ids": seen_employee_ids,
                },
                row_errors=row_errors,
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
        branch: Branch,
        seen_values: dict[str, set[str]],
        row_errors: dict[str, list[str]],
    ) -> dict[str, Any]:
        name = self._text_value(row, "name")
        email = self._text_value(row, "email")
        employee_id = self._text_value(row, "employee_id")
        father_name = self._text_value(row, "father_name")
        grandfather_name = self._text_value(row, "grandfather_name")
        phone_number = self._text_value(row, "phone_number")
        specialization = self._text_value(row, "specialization")
        bio = self._text_value(row, "bio")
        joining_date = self._resolve_joining_date(
            row.get("joining_date"),
            row_errors,
        )

        if not name:
            row_errors["name"] = ["Name is required."]
        if not father_name:
            row_errors["father_name"] = ["Father name is required."]
        if not grandfather_name:
            row_errors["grandfather_name"] = ["Grandfather name is required."]

        self._validate_email(email, row_errors, seen_values["emails"])
        employee_id = self._validate_employee_id(
            employee_id,
            row_errors,
            seen_values["employee_ids"],
        )
        self._validate_phone_number(phone_number, row_errors)

        return {
            "name": name,
            "email": email,
            "employee_id": employee_id,
            "joining_date": joining_date,
            "father_name": father_name,
            "grandfather_name": grandfather_name,
            "phone_number": phone_number,
            "specialization": specialization,
            "bio": bio,
            "branch": branch,
        }

    def _validate_email(
        self,
        email: str,
        row_errors: dict[str, list[str]],
        seen_emails: set[str],
    ) -> None:
        if not email:
            row_errors["email"] = ["Email is required."]
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
        if User.objects.filter(email__iexact=email).exists():
            row_errors["email"] = ["A user with this email already exists."]

    def _validate_employee_id(
        self,
        employee_id: str,
        row_errors: dict[str, list[str]],
        seen_employee_ids: set[str],
    ) -> str:
        if not employee_id:
            return f"EMP-{uuid.uuid4().hex[:8].upper()}"

        normalized_employee_id = employee_id.lower()
        if normalized_employee_id in seen_employee_ids:
            row_errors["employee_id"] = ["Duplicate Employee ID in the sheet."]
            return employee_id

        seen_employee_ids.add(normalized_employee_id)
        if Teacher.objects.filter(employee_id__iexact=employee_id).exists():
            row_errors["employee_id"] = [
                "Teacher with this Employee ID already exists.",
            ]

        return employee_id

    def _validate_phone_number(
        self,
        phone_number: str,
        row_errors: dict[str, list[str]],
    ) -> None:
        if not phone_number:
            row_errors["phone_number"] = ["Phone number is required."]
            return

        if User.objects.filter(phone_number=phone_number).exists():
            row_errors["phone_number"] = [
                "A user with this phone number already exists.",
            ]

    def _resolve_joining_date(
        self,
        joining_date_raw: Any,
        row_errors: dict[str, list[str]],
    ):
        if joining_date_raw is None or str(joining_date_raw).strip() == "":
            return timezone.now().date()

        try:
            return pd.to_datetime(joining_date_raw).date()
        except DATE_PARSE_EXCEPTIONS:
            row_errors["joining_date"] = ["Invalid date format. Use YYYY-MM-DD."]
            return None

    def _create_teachers(
        self,
        prepared_rows: list[dict[str, Any]],
        organization: Organization,
        branch: Branch,
    ) -> None:
        try:
            with transaction.atomic():
                for row_data in prepared_rows:
                    user = User.objects.create_user(
                        email=row_data["email"],
                        name=row_data["name"],
                        father_name=row_data["father_name"],
                        grandfather_name=row_data["grandfather_name"],
                        phone_number=row_data["phone_number"] or None,
                        role=User.Role.TEACHER,
                    )
                    user.set_unusable_password()
                    user.save()

                    Teacher.objects.create(
                        user=user,
                        organization=organization,
                        branch=branch,
                        employee_id=row_data["employee_id"],
                        joining_date=row_data["joining_date"],
                        specialization=row_data["specialization"],
                        bio=row_data["bio"],
                    )
        except DatabaseError as exc:
            self.errors.append(
                self._error(0, "server", f"Internal error: {exc!s}"),
            )

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

from django.db import migrations


PHONE_NUMBER_MIN_DIGITS = 10
PHONE_NUMBER_MAX_DIGITS = 15


def normalize_phone_number(phone_number: str) -> str:
    stripped = phone_number.strip()
    if not stripped:
        message = "Phone number is required."
        raise ValueError(message)

    digits = "".join(character for character in stripped if character.isdigit())
    if not digits:
        message = "Phone number must contain digits."
        raise ValueError(message)
    if len(digits) < PHONE_NUMBER_MIN_DIGITS or len(digits) > PHONE_NUMBER_MAX_DIGITS:
        message = "Phone number must contain between 10 and 15 digits."
        raise ValueError(message)

    return f"+{digits}"


def normalize_existing_user_phone_numbers(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    conflicts: dict[str, list[tuple[str, str]]] = {}
    normalized_rows: list[tuple[str, str | None]] = []
    seen_by_phone: dict[str, list[tuple[str, str]]] = {}

    for user in User.objects.exclude(phone_number__isnull=True).exclude(phone_number=""):
        try:
            normalized_phone_number = normalize_phone_number(user.phone_number)
        except ValueError:
            normalized_rows.append((str(user.pk), None))
            continue

        normalized_rows.append((str(user.pk), normalized_phone_number))
        seen_by_phone.setdefault(normalized_phone_number, []).append(
            (str(user.pk), user.phone_number),
        )

    for normalized_phone_number, values in seen_by_phone.items():
        if len(values) > 1:
            conflicts[normalized_phone_number] = values

    if conflicts:
        details = "; ".join(
            f"{phone}: {values}"
            for phone, values in sorted(conflicts.items())
        )
        raise RuntimeError(
            "Cannot normalize user phone numbers because canonical collisions exist: "
            f"{details}",
        )

    for user_id, normalized_phone_number in normalized_rows:
        User.objects.filter(pk=user_id).update(phone_number=normalized_phone_number)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_parentloginotp"),
    ]

    operations = [
        migrations.RunPython(
            normalize_existing_user_phone_numbers,
            migrations.RunPython.noop,
        ),
    ]

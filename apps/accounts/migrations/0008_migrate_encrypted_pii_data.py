from django.db import migrations

from core.services.pii import build_lookup_hash
from core.services.pii import normalize_email_value
from core.services.pii import normalize_phone_number


def migrate_phone_number(phone_number):
    if phone_number is None:
        return None, None

    stripped = phone_number.strip()
    if not stripped:
        return None, None

    try:
        normalized_phone = normalize_phone_number(stripped)
    except ValueError:
        # Preserve dirty legacy data in the encrypted column, but skip the
        # exact-match lookup hash because it depends on a valid normalized value.
        return stripped, None

    return normalized_phone, build_lookup_hash(
        normalized_phone,
        context="accounts.user.phone_number",
    )


def forwards(apps, schema_editor):
    User = apps.get_model("accounts", "User")

    for user in User.objects.all().iterator():
        normalized_email = normalize_email_value(user.old_email) if user.old_email else None
        normalized_phone, phone_lookup_hash = migrate_phone_number(user.old_phone_number)
        user.email = normalized_email
        user.email_lookup_hash = build_lookup_hash(
            normalized_email,
            context="accounts.user.email",
        )
        user.name = user.old_name
        user.father_name = user.old_father_name
        user.grandfather_name = user.old_grandfather_name
        user.phone_number = normalized_phone
        user.phone_lookup_hash = phone_lookup_hash
        user.address = user.old_address
        user.save(
            update_fields=[
                "email",
                "email_lookup_hash",
                "name",
                "father_name",
                "grandfather_name",
                "phone_number",
                "phone_lookup_hash",
                "address",
            ],
        )


def reverse(apps, schema_editor):
    User = apps.get_model("accounts", "User")

    for user in User.objects.all().iterator():
        user.old_email = user.email
        user.old_name = user.name
        user.old_father_name = user.father_name
        user.old_grandfather_name = user.grandfather_name
        user.old_phone_number = user.phone_number
        user.old_address = user.address
        user.save(
            update_fields=[
                "old_email",
                "old_name",
                "old_father_name",
                "old_grandfather_name",
                "old_phone_number",
                "old_address",
            ],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_add_encrypted_pii_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]

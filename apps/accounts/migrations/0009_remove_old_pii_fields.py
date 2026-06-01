from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_migrate_encrypted_pii_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="user",
            name="old_email",
        ),
        migrations.RemoveField(
            model_name="user",
            name="old_name",
        ),
        migrations.RemoveField(
            model_name="user",
            name="old_father_name",
        ),
        migrations.RemoveField(
            model_name="user",
            name="old_grandfather_name",
        ),
        migrations.RemoveField(
            model_name="user",
            name="old_phone_number",
        ),
        migrations.RemoveField(
            model_name="user",
            name="old_address",
        ),
    ]

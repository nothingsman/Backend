from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_parentloginotp"),
    ]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="email",
            new_name="old_email",
        ),
        migrations.RenameField(
            model_name="user",
            old_name="name",
            new_name="old_name",
        ),
        migrations.RenameField(
            model_name="user",
            old_name="father_name",
            new_name="old_father_name",
        ),
        migrations.RenameField(
            model_name="user",
            old_name="grandfather_name",
            new_name="old_grandfather_name",
        ),
        migrations.RenameField(
            model_name="user",
            old_name="phone_number",
            new_name="old_phone_number",
        ),
        migrations.RenameField(
            model_name="user",
            old_name="address",
            new_name="old_address",
        ),
    ]

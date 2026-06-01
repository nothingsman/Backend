import core.fields
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_rename_pii_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email",
            field=core.fields.EncryptedEmailField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name="Email Address",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="email_lookup_hash",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=64,
                null=True,
                unique=True,
                verbose_name="Email Lookup Hash",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="name",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=255,
                verbose_name="First Name",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="father_name",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=255,
                verbose_name="Father's Name",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="grandfather_name",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=255,
                verbose_name="Grandfather's Name",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="phone_number",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=20,
                null=True,
                verbose_name="Phone Number",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="phone_lookup_hash",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=64,
                null=True,
                unique=True,
                verbose_name="Phone Lookup Hash",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="address",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=255,
                verbose_name="Address",
            ),
        ),
    ]

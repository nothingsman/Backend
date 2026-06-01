from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="attendance",
            options={
                "ordering": ["-date", "section__name", "student__roll_no"],
                "verbose_name": "Attendance",
                "verbose_name_plural": "Attendance Records",
            },
        ),
    ]

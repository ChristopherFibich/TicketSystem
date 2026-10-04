from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0021_useravailabilityevent_is_absent_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserActivity",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("last_seen", models.DateTimeField(db_index=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activity",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]

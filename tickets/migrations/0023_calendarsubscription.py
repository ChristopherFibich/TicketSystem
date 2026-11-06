from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
	dependencies = [
		("tickets", "0022_useractivity"),
	]

	operations = [
		migrations.CreateModel(
			name="CalendarSubscription",
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
				("name", models.CharField(max_length=100)),
				("url", models.URLField(max_length=1000)),
				("created_at", models.DateTimeField(auto_now_add=True)),
				(
					"user",
					models.ForeignKey(
						on_delete=django.db.models.deletion.CASCADE,
						related_name="calendar_subscriptions",
						to=settings.AUTH_USER_MODEL,
					),
				),
			],
			options={
				"ordering": ["name", "id"],
			},
		),
		migrations.AddConstraint(
			model_name="calendarsubscription",
			constraint=models.UniqueConstraint(
				fields=("user", "url"),
				name="unique_calendar_subscription_url",
			),
		),
	]
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
	dependencies = [
		("tickets", "0025_remove_calendarsubscription_color"),
	]

	operations = [
		migrations.CreateModel(
			name="CalendarEvent",
			fields=[
				("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
				("title", models.CharField(max_length=200)),
				("starts_at", models.DateTimeField(db_index=True)),
				("ends_at", models.DateTimeField()),
				("published_at", models.DateTimeField(blank=True, null=True)),
				("created_at", models.DateTimeField(auto_now_add=True)),
				(
					"created_by",
					models.ForeignKey(
						on_delete=django.db.models.deletion.CASCADE,
						related_name="calendar_events_created",
						to=settings.AUTH_USER_MODEL,
					),
				),
			],
			options={"ordering": ["starts_at", "id"]},
		),
		migrations.CreateModel(
			name="CalendarInvitation",
			fields=[
				("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
				(
					"response",
					models.CharField(
						choices=[("PENDING", "Pending"), ("ACCEPTED", "Accepted"), ("DECLINED", "Declined")],
						default="PENDING",
						max_length=10,
					),
				),
				("responded_at", models.DateTimeField(blank=True, null=True)),
				(
					"event",
					models.ForeignKey(
						on_delete=django.db.models.deletion.CASCADE,
						related_name="invitations",
						to="tickets.calendarevent",
					),
				),
				(
					"ticket",
					models.OneToOneField(
						on_delete=django.db.models.deletion.CASCADE,
						related_name="calendar_invitation",
						to="tickets.ticket",
					),
				),
				(
					"user",
					models.ForeignKey(
						on_delete=django.db.models.deletion.CASCADE,
						related_name="calendar_invitations",
						to=settings.AUTH_USER_MODEL,
					),
				),
			],
		),
		migrations.AddConstraint(
			model_name="calendarinvitation",
			constraint=models.UniqueConstraint(fields=("event", "user"), name="unique_calendar_invitation_user"),
		),
	]
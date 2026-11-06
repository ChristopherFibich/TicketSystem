from django.db import migrations


class Migration(migrations.Migration):
	dependencies = [
		("tickets", "0024_calendarsubscription_color"),
	]

	operations = [
		migrations.RemoveField(
			model_name="calendarsubscription",
			name="color",
		),
	]
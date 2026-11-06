from django.db import migrations, models


class Migration(migrations.Migration):
	dependencies = [
		("tickets", "0026_calendarevent_calendarinvitation"),
	]

	operations = [
		migrations.AddField(
			model_name="calendarevent",
			name="notes",
			field=models.TextField(blank=True),
		),
	]
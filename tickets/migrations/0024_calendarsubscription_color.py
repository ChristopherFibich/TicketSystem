from django.db import migrations, models


class Migration(migrations.Migration):
	dependencies = [
		("tickets", "0023_calendarsubscription"),
	]

	operations = [
		migrations.AddField(
			model_name="calendarsubscription",
			name="color",
			field=models.CharField(default="#4285F4", max_length=7),
		),
	]
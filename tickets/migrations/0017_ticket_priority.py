from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		('tickets', '0016_graphs_group_membership'),
	]

	operations = [
		migrations.AddField(
			model_name='ticket',
			name='priority',
			field=models.CharField(choices=[('LOW', 'Low'), ('MED', 'Med'), ('HIGH', 'High')], default='MED', max_length=10),
		),
	]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("occurrences", "0004_remove_occurrence_weather")]

    operations = [
        migrations.AlterField(
            model_name="occurrence",
            name="neighborhood",
            field=models.CharField(max_length=255),
        ),
    ]

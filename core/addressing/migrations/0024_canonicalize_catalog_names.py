from django.db import migrations


SMALL_WORDS = {"a", "ao", "aos", "as", "da", "das", "de", "do", "dos", "e", "em", "na", "nas", "no", "nos"}


def title_case(value):
    words = (value or "").strip().split()
    formatted = []
    for index, word in enumerate(words):
        lower = word.casefold()
        if index > 0 and lower in SMALL_WORDS:
            formatted.append(lower)
            continue
        formatted.append("-".join(part[:1].upper() + part[1:].lower() for part in lower.split("-")))
    return " ".join(formatted)


def canonicalize(apps, schema_editor):
    Street = apps.get_model("addressing", "Street")
    Neighborhood = apps.get_model("addressing", "Neighborhood")
    Region = apps.get_model("addressing", "Region")
    for model in (Street, Neighborhood, Region):
        for obj in model.objects.all().iterator():
            value = title_case(obj.name)
            if value and value != obj.name:
                obj.name = value
                obj.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [("addressing", "0023_street_official_constraint")]
    operations = [migrations.RunPython(canonicalize, migrations.RunPython.noop)]

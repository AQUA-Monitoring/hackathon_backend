from django.db import migrations, models


def consolidate_streets(apps, schema_editor):
    Street = apps.get_model("addressing", "Street")
    RoadAxisSegment = apps.get_model("addressing", "RoadAxisSegment")
    StreetNeighborhood = apps.get_model("addressing", "StreetNeighborhood")
    AddressReference = apps.get_model("addressing", "AddressReference")
    Address = apps.get_model("addressing", "Address")
    # Primeiro recupera o código oficial preservado na proveniência bruta. Sem
    # código, a rua permanece independente (nomes iguais não constituem identidade).
    for street in Street.objects.filter(official_code="").iterator():
        props = street.properties or {}
        code = str(props.get("official_code") or props.get("codlogra") or "").strip()
        updates = []
        if code:
            street.official_code = code
            updates.append("official_code")
        if not street.source_name:
            street.source_name = str(props.get("name") or props.get("nome") or street.name or "").strip()
            updates.append("source_name")
        if updates:
            street.save(update_fields=updates)

    rows = Street.objects.exclude(official_code="").order_by("city_id", "dataset_id", "official_code", "created_at", "id")
    canonical = {}
    for street in rows.iterator():
        key = (street.city_id, street.dataset_id, street.official_code)
        winner = canonical.get(key)
        if winner is None:
            canonical[key] = street
            if not street.source_name:
                street.source_name = street.name
                street.save(update_fields=["source_name"])
            continue
        RoadAxisSegment.objects.filter(street_id=street.id).update(street_id=winner.id)
        for link in StreetNeighborhood.objects.filter(street_id=street.id):
            if StreetNeighborhood.objects.filter(street_id=winner.id, neighborhood_id=link.neighborhood_id).exists():
                link.delete()
            else:
                link.street_id = winner.id
                link.save(update_fields=["street_id"])
        AddressReference.objects.filter(street_id=street.id).update(street_id=winner.id)
        Address.objects.filter(street_ref_id=street.id).update(street_ref_id=winner.id)
        # Preserva a linha para auditoria e evita remoção destrutiva.
        street.is_active = False
        street.save(update_fields=["is_active"])


class Migration(migrations.Migration):
    dependencies = [("addressing", "0021_address_reference_autocomplete_indexes")]
    operations = [
        migrations.AddField(model_name="street", name="official_code", field=models.CharField(blank=True, db_index=False, max_length=80)),
        migrations.AddField(model_name="street", name="source_name", field=models.CharField(blank=True, max_length=255)),
        migrations.RunPython(consolidate_streets, migrations.RunPython.noop),
    ]

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Wrapper compatível para limites oficiais de bairros; não infere regiões."

    def add_arguments(self, parser):
        parser.add_argument("geojson_path")
        parser.add_argument("--city", default="Joinville")
        parser.add_argument("--authority", required=True)
        parser.add_argument("--title", required=True)
        parser.add_argument("--source-url", required=True)
        parser.add_argument("--license-name", required=True)
        parser.add_argument("--license-url", default="")
        parser.add_argument("--source-version", required=True)
        parser.add_argument("--published-at")
        parser.add_argument("--source-crs", default="EPSG:4326")
        parser.add_argument("--id-prop", default="id")
        parser.add_argument("--neighborhood-prop", default="bairro")
        parser.add_argument("--region-prop", default="zona")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--infer-zones-if-missing", action="store_true")

    def handle(self, *args, **options):
        if options.pop("infer_zones_if_missing", False):
            raise CommandError("Inferência de regiões foi removida; importe somente regiões oficiais")
        path = options.pop("geojson_path")
        options["kind"] = "neighborhood_boundary"
        options["name_prop"] = options.pop("neighborhood_prop")
        call_command("import_addressing_dataset", path, **options)

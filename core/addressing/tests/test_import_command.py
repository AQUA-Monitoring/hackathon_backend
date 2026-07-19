import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.core.management.base import CommandError
from django.utils import timezone

from django.contrib.gis.geos import MultiPolygon, Polygon

from core.addressing.infra.models import AddressReference, City, GeodataDataset, Neighborhood, RoadAxisSegment, Street, StreetNeighborhood
from core.addressing.management.commands.import_addressing_dataset import chunked, geos_geometry, iter_source_features


class AddressingImportCommandTests(TestCase):
    def setUp(self):
        City.objects.get_or_create(name="Joinville", defaults={"official_code": "4209102", "normalized_name": "joinville"})
        self.payload = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": "b1", "bairro": "Centro"}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}}]}

    def _file(self, directory):
        path = Path(directory) / "bairros.geojson"
        path.write_text(json.dumps(self.payload), encoding="utf-8")
        return path

    def _options(self):
        return {"city": "Joinville", "kind": "neighborhood_boundary", "authority": "Prefeitura", "title": "Bairros", "source_url": "https://example.test/bairros", "license_name": "Licença oficial", "source_version": "1", "id_prop": "id", "name_prop": "bairro"}

    def test_dry_run_validates_without_writes(self):
        with TemporaryDirectory() as directory:
            call_command("import_addressing_dataset", str(self._file(directory)), dry_run=True, **self._options())
        self.assertEqual(GeodataDataset.objects.count(), 0)
        self.assertEqual(Neighborhood.objects.count(), 0)

    def test_same_file_is_idempotent(self):
        with TemporaryDirectory() as directory:
            path = self._file(directory)
            call_command("import_addressing_dataset", str(path), **self._options())
            call_command("import_addressing_dataset", str(path), **self._options())
        self.assertEqual(GeodataDataset.objects.count(), 1)
        self.assertEqual(Neighborhood.objects.count(), 1)

    def test_canonical_city_code_and_crs_aliases(self):
        with TemporaryDirectory() as directory:
            options = self._options()
            options.pop("city")
            call_command("import_addressing_dataset", str(self._file(directory)), city_code="4209102", crs="EPSG:4326", **options)
        self.assertEqual(Neighborhood.objects.get().normalized_name, "centro")

    def test_invalid_geometry_is_strict_and_repair_is_audited(self):
        self.payload["features"][0]["geometry"]["coordinates"] = [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]
        with TemporaryDirectory() as directory:
            path = self._file(directory)
            with self.assertRaises(CommandError):
                call_command("import_addressing_dataset", str(path), **self._options())
            call_command("import_addressing_dataset", str(path), repair_geometries=True, **self._options())
        dataset = GeodataDataset.objects.get()
        self.assertEqual(dataset.status, "active")
        self.assertEqual(len(dataset.metadata["report"]["repairs"]), 1)
        self.assertEqual(dataset.metadata["report"]["errors"], 0)

    def test_csv_cnefe_fields_and_complete_report(self):
        city = City.objects.get(name="Joinville")
        city.geometry = MultiPolygon(Polygon(((-1, -1), (2, -1), (2, 2), (-1, 2), (-1, -1))), srid=4326)
        city.save(update_fields=["geometry"])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cnefe.csv"
            path.write_text("id,street,number,modifier,address_type,species,complement,zipcode,longitude,latitude\na1,Rua A,10,A,urbano,domicilio,fundos,89200-000,0.5,0.5\n", encoding="utf-8")
            call_command("import_addressing_dataset", str(path), city_code="4209102", kind="address_point", authority="IBGE", title="CNEFE", source_url="https://example.test/cnefe", license_name="IBGE", source_version="2022", crs="EPSG:4326")
        address = AddressReference.objects.get()
        self.assertEqual((address.modifier, address.address_type, address.species, address.complement), ("A", "urbano", "domicilio", "fundos"))
        report = address.dataset.metadata["report"]
        for field in ("created", "updated", "inactivated", "skipped", "duplicates", "errors", "conflicts", "spatial_links", "unmatched"):
            self.assertIn(field, report)

    def test_reprojects_epsg_31982_with_longitude_latitude_order(self):
        raw = {"type": "Point", "coordinates": [716000, 7095000]}
        geometry, repair = geos_geometry(raw, "EPSG:31982", {"Point"})
        self.assertIsNone(repair)
        self.assertTrue(-50 < geometry.x < -47)
        self.assertTrue(-28 < geometry.y < -25)

    def test_csv_iteration_is_lazy_and_chunked_above_ten_thousand_rows(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "large.csv"
            with path.open("w", encoding="utf-8") as target:
                target.write("id,longitude,latitude\n")
                for index in range(10001):
                    target.write(f"a{index},0.5,0.5\n")
            iterator = iter_source_features(path, {"longitude_prop": "longitude", "latitude_prop": "latitude"})
            self.assertNotIsInstance(iterator, list)
            sizes = [len(batch) for batch in chunked(iterator, 1024)]
        self.assertEqual(sum(sizes), 10001)
        self.assertEqual(sizes[:-1], [1024] * 9)
        self.assertEqual(sizes[-1], 785)

    def test_streaming_failure_rolls_back_prior_chunks_and_keeps_active_version(self):
        city = City.objects.get(name="Joinville")
        old = GeodataDataset.objects.create(city=city, kind="address_point", authority="IBGE", title="Anterior", source_url="https://example.test/old", license_name="IBGE", source_version="2021", retrieved_at=timezone.now(), sha256="f" * 64, source_crs="EPSG:4326", status="active")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.csv"
            path.write_text("id,longitude,latitude\na1,0.5,0.5\na1,0.6,0.6\n", encoding="utf-8")
            with self.assertRaises(CommandError):
                call_command("import_addressing_dataset", str(path), city_code="4209102", kind="address_point", authority="IBGE", title="Nova", source_url="https://example.test/new", license_name="IBGE", source_version="2022", chunk_size=1)
        old.refresh_from_db()
        self.assertEqual(old.status, "active")
        self.assertEqual(AddressReference.objects.count(), 0)
        self.assertEqual(GeodataDataset.objects.get(title="Nova").status, "failed")

    def test_legacy_wrapper_rejects_inferred_regions(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(CommandError):
                call_command("import_joinville_geojson", str(self._file(directory)), infer_zones_if_missing=True, authority="Prefeitura", title="Bairros", source_url="https://example.test/bairros", license_name="Licença oficial", source_version="1")

    def test_imports_spatial_street_links_and_address_neighborhood(self):
        city = City.objects.get(name="Joinville")
        city.geometry = MultiPolygon(Polygon(((-1, -1), (2, -1), (2, 2), (-1, 2), (-1, -1))), srid=4326)
        city.save(update_fields=["geometry"])
        with TemporaryDirectory() as directory:
            neighborhood_path = self._file(directory)
            call_command("import_addressing_dataset", str(neighborhood_path), **self._options())
            street_path = Path(directory) / "streets.geojson"
            street_path.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": "r1", "name": "Rua A"}, "geometry": {"type": "LineString", "coordinates": [[-.5, .5], [1.5, .5]]}}]}), encoding="utf-8")
            call_command("import_addressing_dataset", str(street_path), city="Joinville", kind="street", authority="Prefeitura", title="Ruas", source_url="https://example.test/ruas", license_name="Licença oficial", source_version="1", id_prop="id", name_prop="name")
            self.assertEqual(StreetNeighborhood.objects.filter(street=Street.objects.get(source_record_id="r1")).count(), 1)
            self.assertEqual(RoadAxisSegment.objects.get(source_record_id="r1").neighborhood_links.count(), 1)
            address_path = Path(directory) / "addresses.geojson"
            address_path.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": "a1", "street": "Rua A", "number": "10"}, "geometry": {"type": "Point", "coordinates": [.5, .5]}}]}), encoding="utf-8")
            call_command("import_addressing_dataset", str(address_path), city="Joinville", kind="address_point", authority="IBGE", title="Endereços", source_url="https://example.test/enderecos", license_name="Licença oficial", source_version="2022", id_prop="id")
        self.assertEqual(AddressReference.objects.get(source_record_id="a1").neighborhood.name, "Centro")

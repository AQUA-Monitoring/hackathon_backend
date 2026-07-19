from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CameraRegistrationMigrationTests(TransactionTestCase):
    migrate_from = [
        ("addressing", "0013_seed_joinville_araquari_and_backfill_refs"),
        ("users", "0003_user_profile_picture_fk_and_url"),
        ("flood_camera_monitoring", "0016_remove_legacy_demo_camera"),
    ]
    migrate_to = [
        ("addressing", "0014_address_city_ref"),
        ("users", "0003_user_profile_picture_fk_and_url"),
        (
            "flood_camera_monitoring",
            "0017_camera_registration_and_operational_snapshot",
        ),
    ]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Camera = old_apps.get_model("flood_camera_monitoring", "Camera")
        self.camera_id = Camera.objects.create(
            status=3,
            description="Câmera legada indisponível",
            video_hls="https://legacy.example/camera.m3u8",
        ).pk

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_migration_separates_legacy_offline_without_inventing_relations(self):
        Camera = self.apps.get_model("flood_camera_monitoring", "Camera")
        Snapshot = self.apps.get_model(
            "flood_camera_monitoring", "CameraOperationalSnapshot"
        )
        camera = Camera.objects.get(pk=self.camera_id)
        snapshot = Snapshot.objects.get(camera_id=self.camera_id)

        self.assertEqual(camera.status, 1)
        self.assertIsNone(camera.address_id)
        self.assertIsNone(camera.created_by_id)
        self.assertEqual(snapshot.stream_status, "UNAVAILABLE")
        self.assertEqual(snapshot.analysis_status, "NOT_ANALYZED")
        self.assertEqual(snapshot.model_status, "UNKNOWN")

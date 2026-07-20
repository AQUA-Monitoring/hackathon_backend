from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys
from unittest import TestCase

from django.test import override_settings
from django.urls import clear_url_caches, resolve


class LightweightImportTests(TestCase):
    def test_base_urls_do_not_import_opencv_or_torch(self):
        project_root = Path(__file__).resolve().parents[3]
        script = """
import importlib
import os
import sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
importlib.import_module('core.flood_camera_monitoring.presentation.base_urls')
assert not {'cv2', 'torch', 'torchvision'}.intersection(sys.modules)
"""
        subprocess.run(
            [sys.executable, "-c", script],
            cwd=project_root,
            env=os.environ.copy(),
            check=True,
            capture_output=True,
            text=True,
        )

    def test_services_stream_prediction_is_framework_independent(self):
        module = importlib.import_module(
            "core.flood_camera_monitoring.services.stream_prediction"
        )
        self.assertTrue(hasattr(module, "PredictionResult"))


class CeleryCompatibilityTests(TestCase):
    def test_legacy_task_module_exports_canonical_task_objects(self):
        legacy = importlib.import_module("core.flood_camera_monitoring.infra.tasks")
        canonical = importlib.import_module("core.flood_camera_monitoring.tasks")

        self.assertIs(
            legacy.analyze_all_cameras_task,
            canonical.analyze_all_cameras_task,
        )
        self.assertEqual(
            legacy.analyze_all_cameras_task.name,
            "core.flood_camera_monitoring.infra.tasks.analyze_all_cameras_task",
        )

    def test_all_compatibility_task_names_are_registered(self):
        from config.celery import app

        importlib.import_module("core.flood_camera_monitoring.infra.tasks")
        expected = {
            "core.flood_camera_monitoring.infra.tasks.analyze_all_cameras_task",
            "core.flood_camera_monitoring.infra.tasks.refresh_predict_all_cache_task",
            "core.flood_camera_monitoring.tasks.refresh_all_and_cache_task",
        }
        self.assertTrue(expected.issubset(app.tasks))


class RoutingCharacterizationTests(TestCase):
    @override_settings(
        ROOT_URLCONF="core.flood_camera_monitoring.presentation.flood_urls"
    )
    def test_direct_urls_keep_camera_contract(self):
        clear_url_caches()
        match = resolve("/cameras/")
        self.assertEqual(match.view_name, "cameras-list")

    @override_settings(
        ROOT_URLCONF="core.flood_camera_monitoring.presentation.proxy_urls"
    )
    def test_proxy_url_keeps_gateway_contract(self):
        clear_url_caches()
        match = resolve("/arbitrary/path")
        self.assertEqual(match.view_name, "flood-camera-proxy")

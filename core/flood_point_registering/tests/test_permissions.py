from django.test import TestCase
from rest_framework.test import APIClient

from core.users.infra.models import User


class FloodPointPermissionsTests(TestCase):
    def test_write_requires_admin(self):
        client = APIClient()
        self.assertEqual(client.post("/api/floods_point/registering/", {}, format="json").status_code, 401)
        client.force_authenticate(User.objects.create(name="Operador", email="operator-point@example.test"))
        self.assertEqual(client.post("/api/floods_point/registering/", {}, format="json").status_code, 403)

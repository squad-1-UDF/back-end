from django.test import SimpleTestCase
from django.urls import reverse


class HealthEndpointTests(SimpleTestCase):
    def test_health_returns_ok_without_database(self):
        response = self.client.get(reverse("api-health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "labtech-api"})

    def test_health_is_read_only(self):
        response = self.client.post(reverse("api-health"))
        self.assertEqual(response.status_code, 405)

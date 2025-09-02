from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from core.models import Ingredient

class PantryTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("demo", password="pass12345")
        self.client.login(username="demo", password="pass12345")

    def test_add_ingredient(self):
        resp = self.client.post(reverse("add_ingredient"), {
            "name": "tomato", "quantity": "2", "unit": "pcs"
        })
        self.assertRedirects(resp, reverse("dashboard"))
        self.assertTrue(Ingredient.objects.filter(user=self.u, name="tomato").exists())

    def test_dashboard_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)

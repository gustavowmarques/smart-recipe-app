from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Ingredient
import json

class SpoonacularWebRecipesTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("demo", password="pass12345")
        self.client.login(username="demo", password="pass12345")
        Ingredient.objects.create(user=self.u, name="chicken")

    @patch("core.views.requests.get")
    def test_web_recipes_success(self, mock_get):
        # Mock 1: findByIngredients
        find_payload = [
            {"id": 1, "title": "Chicken Dinner", "image": "http://img", "usedIngredientCount": 1, "missedIngredientCount": 0}
        ]
        find_resp = MagicMock(status_code=200, json=lambda: find_payload)

        # Mock 2: informationBulk
        info_payload = [
            {"id": 1, "title": "Chicken Dinner", "image": "http://img", "sourceUrl": "https://example.com", "readyInMinutes": 30, "servings": 2}
        ]
        info_resp = MagicMock(status_code=200, json=lambda: info_payload)

        mock_get.side_effect = [find_resp, info_resp]

        r = self.client.post(reverse("web_recipes"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Chicken Dinner")
        self.assertContains(r, "Open Recipe")

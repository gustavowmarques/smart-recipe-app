import json
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils.html import escape

from core.models import Ingredient, SavedRecipe

User = get_user_model()


class _MockResponse:
    def __init__(self, json_data=None, status=200, text="OK"):
        self._json = json_data or {}
        self.status_code = status
        self.text = text

    def json(self):
        return self._json


class DashboardAuthTests(TestCase):
    def test_dashboard_requires_login(self):
        url = reverse("core:dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])


class SpoonacularWebRecipesTests(TestCase):
    """Integration-ish tests for the 'web_recipes' flow with mocked HTTP.

    Verifies:
        - 200 response on happy path
        - HTML-escaped title is rendered
        - detail link uses '/web/recipes/<id>/' shape expected by templates
    """

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.client.login(username="testuser", password="pass123")
        Ingredient.objects.create(user=self.user, name="bell pepper")
        Ingredient.objects.create(user=self.user, name="chicken breast")
        Ingredient.objects.create(user=self.user, name="onion")

    @patch.dict("os.environ", {"SPOONACULAR_API_KEY": "spoon-test"})
    @patch("core.views.requests.get")
    def test_web_recipes_success(self, mock_get):
        """Happy path: mocked Spoonacular responses, expect 200 and recipe on page."""

        def side_effect(url, params=None, timeout=None):
            if "findByIngredients" in url:
                return _MockResponse(
                    [
                        {
                            "id": 1234,
                            "title": "Chicken & Peppers",
                            "image": "https://img.test/chicken.jpg",
                            "usedIngredientCount": 2,
                            "usedIngredients": [
                                {"name": "bell pepper"},
                                {"name": "chicken breast"},
                            ],
                            "missedIngredients": [{"name": "garlic"}],
                        }
                    ],
                    200,
                )
            if "informationBulk" in url:
                return _MockResponse(
                    [
                        {
                            "id": 1234,
                            "title": "Chicken & Peppers",
                            "image": "https://img.test/chicken.jpg",
                            "readyInMinutes": 30,
                            "servings": 2,
                            "dishTypes": ["dinner"],
                            "extendedIngredients": [
                                {"original": "2 bell peppers"},
                                {"original": "300g chicken breast"},
                            ],
                            "analyzedInstructions": [
                                {
                                    "steps": [
                                        {"step": "Cook chicken."},
                                        {"step": "Add peppers."},
                                    ]
                                }
                            ],
                        }
                    ],
                    200,
                )
            return _MockResponse({}, 404, "not found")

        mock_get.side_effect = side_effect

        url = reverse("core:web_recipes")
        r = self.client.post(url, data={"kind": "food"})
        self.assertEqual(r.status_code, 200)
        # HTML escapes & -> &amp; in templates
        self.assertContains(r, escape("Chicken & Peppers"))
        # View link present
        self.assertContains(r, "/web/recipes/1234/")


class AIRecipesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="aiuser", password="pass123")
        self.client.login(username="aiuser", password="pass123")
        Ingredient.objects.create(user=self.user, name="bell pepper")
        Ingredient.objects.create(user=self.user, name="chicken breast")
        Ingredient.objects.create(user=self.user, name="onion")

    @patch.dict(
        "os.environ", {"OPENAI_API_KEY": "sk-test", "SPOONACULAR_API_KEY": "spoon-test"}
    )
    @patch("core.views.requests.get")
    @patch("core.views.requests.post")
    def test_ai_recipes_happy_path(self, mock_post, mock_get):
        """Mock OpenAI JSON + Spoonacular fallback image. Expect 200 and titles on page."""
        ai_payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "recipes": [
                                    {
                                        "title": "Pepper Chicken Bake",
                                        "ingredients": [
                                            "bell pepper",
                                            "chicken breast",
                                            "onion",
                                        ],
                                        "steps": ["Prep", "Bake"],
                                        "tags": ["baked"],
                                        "cook_time_minutes": 40,
                                    }
                                    for _ in range(4)
                                ]
                            }
                        )
                    }
                }
            ]
        }
        mock_post.return_value = _MockResponse(ai_payload, 200)
        mock_get.return_value = _MockResponse(
            {"results": [{"image": "https://img.test/fallback.jpg"}]}, 200
        )

        url = reverse("core:ai_recipes")
        r = self.client.post(url, data={"kind": "food"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "AI Recipe Ideas")
        self.assertContains(r, "Pepper Chicken Bake")


class FavoritesDBDetailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="favuser", password="pass123")
        self.client.login(username="favuser", password="pass123")

    def test_favorite_detail_renders_without_session(self):
        fav = SavedRecipe.objects.create(
            user=self.user,
            source="ai",
            external_id="1",
            title="Saved Pepper Chicken",
            image_url="https://img.test/saved.jpg",
            ingredients_json=["bell pepper", "chicken"],
            steps_json=["Prep", "Bake"],
        )
        url = reverse("core:favorite_detail", args=[fav.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Saved Pepper Chicken")
        self.assertContains(r, "Ingredients")
        self.assertContains(r, "Instructions")

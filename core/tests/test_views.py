import json
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import Ingredient, SavedRecipe

User = get_user_model()

# Simple response stub
class MockResponse:
    def __init__(self, json_data=None, status=200, text="OK"):
        self._json = json_data or {}
        self.status_code = status
        self.text = text
    def json(self):
        return self._json

class ViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="pass123")
        # Pantry items
        Ingredient.objects.create(user=self.user, name="bell pepper")
        Ingredient.objects.create(user=self.user, name="chicken breast")
        Ingredient.objects.create(user=self.user, name="onion")

    def test_dashboard_requires_login(self):
        url = reverse("dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_dashboard_authenticated(self):
        self.client.login(username="bob", password="pass123")
        url = reverse("dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Your Pantry")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test", "SPOONACULAR_API_KEY": "spoon-test"})
    @patch("core.views.requests.get")
    @patch("core.views.requests.post")
    def test_ai_recipes_happy_path(self, mock_post, mock_get):
        """
        Mocks OpenAI chat completion (JSON recipe output) and Spoonacular image fallback.
        Verifies page renders and shows at least one recipe card.
        """
        self.client.login(username="bob", password="pass123")

        # Mock OpenAI chat completion JSON
        ai_payload = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "recipes": [{
                            "title": "Pepper Chicken Bake",
                            "ingredients": ["bell pepper", "chicken breast", "onion"],
                            "steps": ["Prep", "Bake"],
                            "tags": ["baked"],
                            "cook_time_minutes": 40
                        } for _ in range(4)]
                    })
                }
            }]
        }
        mock_post.return_value = MockResponse(ai_payload, 200)

        # Mock Spoonacular complexSearch for fallback image (called once per recipe)
        spoon_payload = {"results": [{"image": "https://img.test/fallback.jpg"}]}
        mock_get.return_value = MockResponse(spoon_payload, 200)

        url = reverse("ai_recipes")
        resp = self.client.post(url, data={"kind": "food"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "AI Recipe Ideas")
        self.assertContains(resp, "Pepper Chicken Bake")

    @patch.dict("os.environ", {"SPOONACULAR_API_KEY": "spoon-test"})
    @patch("core.views.requests.get")
    def test_web_recipes_happy_path(self, mock_get):
        """
        Mocks Spoonacular findByIngredients + informationBulk.
        Verifies web results page renders and shows a result.
        """
        self.client.login(username="bob", password="pass123")

        # findByIngredients
        find_results = [
            {
                "id": 1234,
                "title": "Chicken & Peppers",
                "image": "https://img.test/chicken.jpg",
                "usedIngredientCount": 2,
                "usedIngredients": [{"name": "bell pepper"}, {"name": "chicken breast"}],
                "missedIngredients": [{"name": "garlic"}],
            }
        ]
        # informationBulk
        info_results = [
            {
                "id": 1234,
                "title": "Chicken & Peppers",
                "image": "https://img.test/chicken.jpg",
                "readyInMinutes": 30,
                "servings": 2,
                "dishTypes": ["dinner"],
                "extendedIngredients": [{"original": "2 bell peppers"}, {"original": "300g chicken breast"}],
                "analyzedInstructions": [{"steps": [{"step": "Cook chicken."}, {"step": "Add peppers."}]}],
            }
        ]

        def side_effect(url, params=None, timeout=None):
            if "findByIngredients" in url:
                return MockResponse(find_results, 200)
            if "informationBulk" in url:
                return MockResponse(info_results, 200)
            return MockResponse({}, 404, "Not found")

        mock_get.side_effect = side_effect

        url = reverse("web_recipes")
        resp = self.client.post(url, data={"kind": "food"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Chicken & Peppers")

    def test_favorite_detail_renders_without_session(self):
        """
        favorite_detail should render a recipe from DB only.
        """
        self.client.login(username="bob", password="pass123")
        fav = SavedRecipe.objects.create(
            user=self.user,
            source="ai",
            external_id="1",
            title="Saved Pepper Chicken",
            image_url="https://img.test/saved.jpg",
            ingredients_json=["bell pepper", "chicken"],
            steps_json=["Prep", "Bake"],
        )
        url = reverse("favorite_detail", args=[fav.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Saved Pepper Chicken")
        self.assertContains(resp, "Ingredients")
        self.assertContains(resp, "Instructions")

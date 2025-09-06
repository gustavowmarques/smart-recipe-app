from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import SavedRecipe

User = get_user_model()

class TemplateSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tina", password="pass123")
        self.client.login(username="tina", password="pass123")

    def test_favorites_page_smoke(self):
        # create one favorite so the grid renders
        SavedRecipe.objects.create(
            user=self.user, source="web", external_id="999",
            title="Web Lasagna",
            image_url="https://img.test/lasagna.jpg",
            ingredients_json=[{"original": "12 lasagna sheets"}],
            steps_json=["Layer", "Bake"],
        )
        resp = self.client.get(reverse("favorites"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Your Favorites")
        self.assertContains(resp, "Web Lasagna")

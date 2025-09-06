from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import SavedRecipe

User = get_user_model()

class SavedRecipeModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass123")

    def test_create_saved_recipe_minimal(self):
        obj = SavedRecipe.objects.create(
            user=self.user,
            source="ai",
            external_id="1",
            title="Stuffed Bell Peppers",
            image_url="https://img.test/pepper.jpg",
            ingredients_json=["bell pepper", "chicken"],
            steps_json=["Prep", "Bake"],
        )
        self.assertEqual(obj.user, self.user)
        self.assertEqual(obj.source, "ai")
        self.assertEqual(obj.external_id, "1")
        self.assertIn("Pepper", obj.title)
        # JSON fields stored as python lists
        self.assertIsInstance(obj.ingredients_json, list)
        self.assertIsInstance(obj.steps_json, list)

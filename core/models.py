from django.conf import settings
from django.db import models

class Ingredient(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ingredients")
    name = models.CharField(max_length=100)
    quantity = models.CharField(max_length=50, blank=True)  # e.g., "2", "200g"
    unit = models.CharField(max_length=20, blank=True)      # e.g., "g", "pcs"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "name")  # simple dedup
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} {self.quantity}{self.unit}".strip()

class SavedRecipe(models.Model):
    SOURCE_CHOICES = (
        ("ai", "AI"),
        ("web", "Web"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_recipes",
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    external_id = models.CharField(
        max_length=64, blank=True
    )  # Spoonacular ID for 'web'; a stable hash or generated id for 'ai'
    title = models.CharField(max_length=200)
    image_url = models.URLField(blank=True)
    ingredients_json = models.JSONField(default=list)
    steps_json = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "source", "external_id")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.source})"
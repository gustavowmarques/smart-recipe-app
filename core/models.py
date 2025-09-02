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

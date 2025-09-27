"""
Core data models for Smart Recipe.

Notes:
- Uses UniqueConstraint (Django ≥4) instead of deprecated `unique_together`.
- Adds case-insensitive uniqueness for Ingredient names per-user.
- Unifies SavedRecipe image access via `get_image_url()`.
- Introduces explicit choices for PantryImageUpload.status.
"""

from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Index
from django.db.models.functions import Lower


class Ingredient(models.Model):
    """
    A pantry ingredient owned by a user.
    We enforce (user, name) uniqueness in a case-insensitive way so
    "Milk" and "milk" don't duplicate for the same user.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ingredients",
        help_text="Owner of this ingredient.",
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name, e.g. 'Chicken breast'.",
    )
    quantity = models.CharField(
        max_length=50, blank=True,
        help_text="Optional quantity text, e.g. '2', '200g'.",
    )
    unit = models.CharField(
        max_length=32, default="pcs", blank=True,
        null=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            # Case-insensitive uniqueness per user
            models.UniqueConstraint(
                Lower("name"), "user",
                name="uniq_ingredient_user_name_ci",
            ),
        ]
        indexes = [
            Index(fields=["user", "name"]),
        ]

    def __str__(self) -> str:
        qty = f" {self.quantity}" if self.quantity else ""
        unit = f"{self.unit}" if self.unit else ""
        return f"{self.name}{qty}{unit}".strip()


class SavedRecipe(models.Model):
    """
    A recipe saved by a user. Source is either:
      - 'web' (e.g. Spoonacular) with external_id = provider id
      - 'ai'  (generated)      with external_id auto-generated UUID

    Ingredients and steps are stored as JSON lists for flexibility.
    Optional nutrition is a JSON object with macros/micros if known.
    """
    SOURCE_AI = "ai"
    SOURCE_WEB = "web"
    SOURCE_CHOICES = (
        (SOURCE_AI, "AI"),
        (SOURCE_WEB, "Web"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_recipes",
    )
    source = models.CharField(
        max_length=10, choices=SOURCE_CHOICES,
        help_text="Origin of the recipe (AI or Web).",
    )
    # Spoonacular ID for 'web'; generated UUID for 'ai'
    external_id = models.CharField(max_length=64, blank=True)

    title = models.CharField(max_length=200)
    image_url = models.URLField(blank=True, null=True)

    ingredients_json = models.JSONField(default=list, blank=True)
    steps_json = models.JSONField(default=list, blank=True)
    nutrition = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source", "external_id"],
                name="uniq_saved_recipe_user_source_extid",
            )
        ]
        indexes = [
            Index(fields=["user", "source"]),
            Index(fields=["source", "external_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.source})"

    def save(self, *args, **kwargs):
        # Auto-generate a stable external_id for AI recipes if not given
        if not self.external_id:
            self.external_id = str(uuid4())
        return super().save(*args, **kwargs)

    # Small convenience for templates/UI: pick the best image field.
    def get_image_url(self) -> str | None:
        """
        Returns the recipe image URL if available (None otherwise).
        """
        return self.image_url or None


class MealPlan(models.Model):
    """
    A weekly plan. `start_date` should represent the start of the week
    (e.g., Monday). You can enforce Monday in forms/clean() if desired.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meal_plans",
    )
    start_date = models.DateField(help_text="Start date for the week (e.g., Monday).")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "start_date"], name="uniq_mealplan_user_start"
            )
        ]
        ordering = ["-start_date"]
        indexes = [
            Index(fields=["user", "start_date"]),
        ]

    def __str__(self) -> str:
        return f"Meal plan {self.start_date} for {self.user}"


class Meal(models.Model):
    """
    A single scheduled meal inside a MealPlan.
    We ensure one entry per (plan, date, meal_type) slot.
    """
    class Slot(models.TextChoices):
        BREAKFAST = "breakfast", "Breakfast"
        LUNCH     = "lunch",     "Lunch"
        DINNER    = "dinner",    "Dinner"
        SNACK     = "snack",     "Snack"

    plan = models.ForeignKey(MealPlan, on_delete=models.CASCADE, related_name="meals")
    date = models.DateField()
    meal_type = models.CharField(max_length=16, choices=Slot.choices)
    recipe = models.ForeignKey("SavedRecipe", null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["plan", "date", "meal_type"], name="unique_meal_slot")
        ]
        ordering = ["date", "meal_type"]
        indexes = [
            Index(fields=["plan", "date"]),
        ]

    def __str__(self) -> str:
        return f"{self.date} {self.meal_type} ({self.plan.user})"


# --- Nutrition Targets ---
from django.conf import settings
from django.db import models

class NutritionTarget(models.Model):
    DIET_CHOICES = [
        ("high_protein", "High Protein"),
        ("balanced", "Balanced"),
        ("keto", "Keto"),
        ("vegetarian", "Vegetarian"),
        ("vegan", "Vegan"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="nutrition_target")
    calories = models.PositiveIntegerField(default=2000)

    # macros (optional grams)
    protein_g = models.PositiveIntegerField(null=True, blank=True)
    carbs_g   = models.PositiveIntegerField(null=True, blank=True)
    fat_g     = models.PositiveIntegerField(null=True, blank=True)

    # optional extras
    fiber_g = models.PositiveIntegerField(null=True, blank=True)
    sugar_g = models.PositiveIntegerField(null=True, blank=True)

    diet_type = models.CharField(max_length=32, choices=DIET_CHOICES, null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"NutritionTarget<{self.user}>"



class PantryImageUpload(models.Model):
    """
    A user-submitted photo of pantry items to be processed by a vision model.
    `results` is expected to store candidate detections, e.g.:
      {
        "candidates": [{"name": "milk", "confidence": 0.87}, ...]
      }
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DONE    = "done",    "Done"
        FAILED  = "failed",  "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="media/pantry_uploads/")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    results = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            Index(fields=["user", "created_at"]),
            Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"Pantry upload {self.id} by {self.user} ({self.status})"

class LoggedMeal(models.Model):
    MEAL_TYPES = [
        ("breakfast", "Breakfast"),
        ("lunch", "Lunch"),
        ("dinner", "Dinner"),
        ("snack", "Snack"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="logged_meals")
    date = models.DateField(auto_now_add=True)
    meal_type = models.CharField(max_length=16, choices=MEAL_TYPES, default="lunch")

    title = models.CharField(max_length=200, blank=True)          # e.g., "Chicken bowl"
    source_recipe_id = models.CharField(max_length=64, blank=True) # if came from a recipe

    calories = models.PositiveIntegerField(default=0)
    protein_g = models.PositiveIntegerField(default=0)
    carbs_g   = models.PositiveIntegerField(default=0)
    fat_g     = models.PositiveIntegerField(default=0)
    fiber_g   = models.PositiveIntegerField(default=0)
    sugar_g   = models.PositiveIntegerField(default=0)

    quantity = models.FloatField(default=1.0)  # multiplier if partial serving

    class Meta:
        indexes = [models.Index(fields=["user", "date"])]
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.user} {self.date}: {self.title or 'Meal'} ({self.calories} kcal)"
    
    class Favorite(models.Model):
        user = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            on_delete=models.CASCADE,
            related_name="favorites",
        )
        # Store a stable ID for the recipe. Use CharField to support both numeric/string IDs.
        recipe_uid = models.CharField(max_length=128)

        # Optional “snapshot” fields to render favorites list quickly
        title = models.CharField(max_length=255, blank=True)
        image_url = models.URLField(blank=True)
        source_url = models.URLField(blank=True)

        added_at = models.DateTimeField(auto_now_add=True)

        class Meta:
            unique_together = ("user", "recipe_uid")
            indexes = [
                models.Index(fields=["user", "recipe_uid"]),
            ]

        def __str__(self):
            return f"{self.user} → {self.recipe_uid}"
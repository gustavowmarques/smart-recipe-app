from django.contrib import admin
from .models import (
    NutritionTarget,
    MealPlan,
    Meal,
    PantryImageUpload,
    Ingredient,
    SavedRecipe,
)


@admin.register(NutritionTarget)
class NutritionTargetAdmin(admin.ModelAdmin):
    list_display = ("user", "calories", "protein_g", "carbs_g", "fat_g")
    search_fields = ("user__username",)


@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ("user", "start_date")
    search_fields = ("user__username",)
    list_filter = ("start_date",)


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ("plan", "date", "meal_type", "recipe")
    list_filter = ("meal_type", "date")
    autocomplete_fields = ("recipe",)


@admin.register(PantryImageUpload)
class PantryImageUploadAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username",)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    """Admin configuration for Ingredient objects (list/search filters)."""

    list_display = ("user", "name", "quantity", "unit", "created_at")
    search_fields = ("name",)
    list_filter = ("user", "unit")


@admin.register(SavedRecipe)
class SavedRecipeAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "source", "external_id", "created_at")
    search_fields = ("title", "user__username", "external_id")
    list_filter = ("source", "user")

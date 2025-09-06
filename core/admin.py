from django.contrib import admin
from .models import Ingredient, SavedRecipe

@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "quantity", "unit", "created_at")
    search_fields = ("name",)
    list_filter = ("user",)

@admin.register(SavedRecipe)
class SavedRecipeAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "source", "external_id", "created_at")
    search_fields = ("title", "external_id")
    list_filter = ("source", "user")

from django.contrib import admin
from .models import Ingredient
@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "quantity", "unit", "created_at")
    search_fields = ("name", "user__username")

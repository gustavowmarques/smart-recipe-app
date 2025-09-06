from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),

    # Pantry
    path("pantry/add/", views.add_ingredient, name="add_ingredient"),
    path("pantry/<int:pk>/delete/", views.delete_ingredient, name="delete_ingredient"),

    # AI + Web recipes (session-backed detail)
    path("ai/recipes/", views.ai_recipes, name="ai_recipes"),
    path("ai/recipes/<int:recipe_id>/", views.recipe_detail, {"source": "ai"}, name="recipe_detail_ai"),
    path("web/recipes/", views.web_recipes, name="web_recipes"),
    path("web/recipes/<int:recipe_id>/", views.recipe_detail, {"source": "web"}, name="recipe_detail_web"),

    # Save favorite (works for both sources)
    path("<str:source>/recipes/<int:recipe_id>/save/", views.save_favorite, name="save_favorite"),

    # Favorites (DB-backed detail)
    path("favorites/", views.favorites_list, name="favorites"),
    path("favorites/<int:pk>/view/", views.favorite_detail, name="favorite_detail"),
    path("favorites/<int:pk>/delete/", views.favorite_delete, name="favorite_delete"),

    # Manual CRUD for SavedRecipe (DB-backed)
    path("recipes/new/", views.recipe_create, name="recipe_create"),
    path("recipes/<int:pk>/edit/", views.recipe_update, name="recipe_update"),
    path("recipes/<int:pk>/delete/", views.recipe_delete, name="recipe_delete"),
    path("recipes/<int:pk>/", views.favorite_detail, name="recipe_detail"),  # <-- FIXED
]

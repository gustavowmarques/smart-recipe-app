from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),

    # Pantry
    path("pantry/add/", views.add_ingredient, name="add_ingredient"),
    path("pantry/<int:pk>/delete/", views.delete_ingredient, name="delete_ingredient"),

    # AI + Web recipes
    path("ai/recipes/", views.ai_recipes, name="ai_recipes"),
    path("ai/recipes/<int:recipe_id>/", views.recipe_detail, {"source": "ai"}, name="recipe_detail_ai"),
    path("web/recipes/", views.web_recipes, name="web_recipes"),
    path("web/recipes/<int:recipe_id>/", views.recipe_detail, {"source": "web"}, name="recipe_detail_web"),

    # Favorites
    path("<str:source>/recipes/<int:recipe_id>/save/", views.save_favorite, name="save_favorite"),
    path("favorites/", views.favorites_list, name="favorites"),
    path("favorites/<int:pk>/delete/", views.favorite_delete, name="favorite_delete"),
]

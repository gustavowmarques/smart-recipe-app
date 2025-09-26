from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    # Home / Dashboard
    path("", views.home, name="home"),
    path("demo/", views.demo_mode, name="demo_mode"),
    path("dashboard/", views.dashboard, name="dashboard"),

    # Pantry (manual CRUD)
    path("pantry/add/", views.add_ingredient, name="add_ingredient"),
    path("pantry/<int:pk>/delete/", views.delete_ingredient, name="delete_ingredient"),


    # --- Unified recipe search flow ---
    # 1) Single entry point: queries Spoonacular + OpenAI with the same inputs
    path("recipes/search/", views.recipes_search, name="recipes_search"),
    # 2) Combined results page showing both AI and Web results
    path("recipes/results/", views.recipes_results, name="recipes_results"),

    # Back-compat: old list endpoints (may redirect to the unified search)
    path("ai/recipes/", views.ai_recipes, name="ai_recipes"),
    path("web/recipes/", views.web_recipes, name="web_recipes"),

    # Session-backed detail pages (now accept slug OR digits)
    path("ai/recipes/<str:recipe_id>/", views.recipe_detail, {"source": "ai"}, name="recipe_detail_ai"),
    path("web/recipes/<str:recipe_id>/", views.recipe_detail, {"source": "web"}, name="recipe_detail_web"),

    # detail for session-backed results (web/ai)
    path("recipes/<str:source>/<int:recipe_id>/", views.recipe_detail, name="recipe_detail"),

    # save to favorites for a session-backed result:
    path("recipes/<str:source>/<slug:recipe_id>/save/", views.save_favorite, name="save_favorite"),

    # Favorites (DB-backed)
    path("favorites/", views.favorites_list, name="favorites"),
    path("favorites/<int:pk>/view/", views.favorite_detail, name="favorite_detail"),
    path("favorites/<int:pk>/delete/", views.favorite_delete, name="favorite_delete"),

    # Manual CRUD for SavedRecipe (DB-backed)
    path("recipes/new/", views.recipe_create, name="recipe_create"),
    path("recipes/<int:pk>/edit/", views.recipe_update, name="recipe_update"),
    path("recipes/<int:pk>/delete/", views.recipe_delete, name="recipe_delete"),

    # Nutrition targets
    path("targets/", views.nutrition_target_upsert, name="nutrition_target"),
    path("targets/reset/", views.nutrition_target_reset, name="nutrition_target_reset"),

    # Meal logging
    path("log-meal/custom/", views.log_custom_meal, name="log_custom_meal"),
    path("log-meal/<slug:recipe_id>/", views.log_recipe_meal, name="log_recipe_meal"),
    path("log-meal/delete/<int:meal_id>/", views.delete_meal, name="delete_meal"),

    # Meal plan
    path("meal-plan/", views.meal_plan_view, name="meal_plan"),
    path("meal-plan/add/", views.meal_add, name="meal_add"),
    path("meal-plan/<int:meal_id>/delete/", views.meal_delete, name="meal_delete"),

    # Pantry image upload → review → commit
    path("pantry/upload/", views.pantry_upload, name="pantry_upload"),
    path("pantry/uploads/", views.pantry_upload_list, name="pantry_upload_list"),
    path("pantry/upload/quick/", views.pantry_upload_quick, name="pantry_upload_quick"),
    path("pantry/review/<int:pk>/", views.pantry_review, name="pantry_review"),
    path("pantry/extract/start/", views.pantry_extract_start, name="pantry_extract_start"),
    path("pantry/extract/<int:upload_id>/review/", views.pantry_extract_review, name="pantry_extract_review"),

    # Used by the dashboard "Upload & Review" form
    path("pantry/upload-to-review/", views.pantry_extract_start, name="pantry_upload_to_review"),

    path("api/s3/presign-upload/", views.presign_s3_upload, name="presign_s3_upload"),

    # About / Contact
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),


]

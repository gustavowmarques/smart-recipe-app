from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("pantry/add/", views.add_ingredient, name="add_ingredient"),
    path("pantry/<int:pk>/delete/", views.delete_ingredient, name="delete_ingredient"),
    path("ai/recipes/", views.ai_recipes, name="ai_recipes"),
]

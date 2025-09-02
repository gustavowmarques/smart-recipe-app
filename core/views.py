from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Ingredient
from .forms import IngredientForm
import os, json
import requests  # for Edamam later (optional)
import logging

logger = logging.getLogger(__name__)

def home(request):
    return render(request, "core/home.html")

@login_required
def dashboard(request):
    ingredients = request.user.ingredients.all()
    form = IngredientForm()
    return render(request, "core/dashboard.html", {"ingredients": ingredients, "form": form})

@login_required
def add_ingredient(request):
    if request.method == "POST":
        form = IngredientForm(request.POST)
        if form.is_valid():
            ing = form.save(commit=False)
            ing.user = request.user
            try:
                ing.save()
                messages.success(request, f"Added {ing.name}.")
            except Exception as e:
                messages.error(request, f"Could not add: {e}")
        else:
            messages.error(request, "Please correct the errors.")
    return redirect("dashboard")

@login_required
def delete_ingredient(request, pk):
    ing = get_object_or_404(Ingredient, pk=pk, user=request.user)
    if request.method == "POST":
        ing.delete()
        messages.info(request, f"Removed {ing.name}.")
    return redirect("dashboard")

# -------- AI Recipes (OpenAI) ----------
import http.client
import base64

@login_required
def ai_recipes(request):
    # Gather user pantry as a list of names
    pantry = list(request.user.ingredients.values_list("name", flat=True))
    if not pantry:
        messages.warning(request, "Your pantry is empty. Add some ingredients first.")
        return redirect("dashboard")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        messages.error(request, "OpenAI API key not configured.")
        return redirect("dashboard")

    # Build a minimal prompt & schema for structured output
    prompt = (
        "You're a professional chef. Given a list of ingredients, create 3 dinner recipes.\n"
        "Rules: prefer using ingredients provided; propose smart substitutions; keep steps simple.\n"
        "Return strictly JSON with fields: recipes: [{title, ingredients:[string], steps:[string], tags:[string], cook_time_minutes:int}]."
        f"\nIngredients: {', '.join(pantry)}"
    )

    # Simple call via REST (keep it dependency-light)
    # If you have the official openai package, feel free to use it instead.
    try:
        import json, urllib.request

        url = "https://api.openai.com/v1/responses"  # Responses API endpoint
        payload = {
            "model": "gpt-4.1-mini",  # small/fast; upgrade later if needed
            "input": prompt,
            "response_format": {  # ask for JSON
                "type": "json_object"
            }
        }
        req = urllib.request.Request(url,
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type":"application/json",
                                              "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Responses returns output under 'output_text' for json_object format
        raw = data.get("output_text", "{}")
        result = json.loads(raw)  # should be {"recipes":[...]}
        recipes = result.get("recipes", [])

        if not recipes:
            messages.warning(request, "AI returned no recipes. Try adding more ingredients.")
            return redirect("dashboard")

        return render(request, "core/ai_results.html", {"recipes": recipes, "pantry": pantry})

    except Exception as e:
        logger.exception("AI error")
        messages.error(request, f"Failed to fetch AI recipes: {e}")
        return redirect("dashboard")

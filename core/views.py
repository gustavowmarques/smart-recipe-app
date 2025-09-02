from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Ingredient
from .forms import IngredientForm
import os, json, logging
import requests  # for Edamam later (optional)

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
    pantry = list(request.user.ingredients.values_list("name", flat=True))
    if not pantry:
        messages.warning(request, "Your pantry is empty. Add some ingredients first.")
        return redirect("dashboard")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        messages.error(request, "OpenAI API key not configured.")
        return redirect("dashboard")

    system_msg = (
        "You are a professional chef. Given pantry items, propose 3 dinner recipes. "
        "Prefer using provided ingredients; suggest smart substitutions if needed. "
        "Return STRICT JSON ONLY with this schema:\n"
        "{"
        "  \"recipes\": ["
        "    {"
        "      \"title\": string,"
        "      \"ingredients\": [string],"
        "      \"steps\": [string],"
        "      \"tags\": [string],"
        "      \"cook_time_minutes\": integer"
        "    }"
        "  ]"
        "}"
    )
    user_msg = f"Pantry items: {', '.join(pantry)}"

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",               # stable, inexpensive
                "response_format": {"type": "json_object"},
                "temperature": 0.7,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            # Show exact server message to help debugging
            logger.error("OpenAI 400+ response: %s", resp.text)
            messages.error(request, f"AI request failed ({resp.status_code}): {resp.text}")
            return redirect("dashboard")

        data = resp.json()
        content = data["choices"][0]["message"]["content"]  # JSON string
        parsed = json.loads(content)
        recipes = parsed.get("recipes", [])
        if not recipes:
            messages.warning(request, "AI returned no recipes. Try adding more ingredients.")
            return redirect("dashboard")

        return render(request, "core/ai_results.html", {"recipes": recipes, "pantry": pantry})

    except requests.RequestException as e:
        logger.exception("Network error calling OpenAI")
        messages.error(request, f"Network error calling AI: {e}")
        return redirect("dashboard")
    except (KeyError, ValueError) as e:
        logger.exception("Failed to parse AI response")
        messages.error(request, f"Failed to parse AI response: {e}")
        return redirect("dashboard")

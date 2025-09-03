# core/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from .models import Ingredient
from .forms import IngredientForm

import os
import json
import logging
import re
import requests

logger = logging.getLogger(__name__)

# ----------------------------
# Tunable matching thresholds
# ----------------------------
# First filter: Spoonacular's own count of matched ingredients.
SPOON_MIN_MATCHED_API = 1      # keep results with >= this many matches (Spoonacular's view)
# Second filter: your strict confirmation against the user's pantry.
SPOON_MIN_CONFIRMED = 1        

# ----------------------------
# Helpers
# ----------------------------
def slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-") or "recipe"

# Synonyms/aliases for relaxed matching
SYNONYMS = {
    "beef": [
        r"\bbeef\b", r"\bground\s+beef\b", r"\bsirloin\b", r"\bsteak\b",
        r"\btop\s+round\b", r"\bchuck\b"
    ],
    "corn": [
        r"\bcorn\b", r"\bsweet\s+corn\b", r"\bcorn\s+on\s+the\s+cob\b", r"\bcorn\s+kernels?\b"
    ],
    "bell pepper": [
        r"\bbell\s+pepper(s)?\b", r"\bred\s+pepper(s)?\b", r"\bgreen\s+pepper(s)?\b",
        r"\byellow\s+pepper(s)?\b", r"\bcapsicum\b"
    ],
}

def is_match(pantry_item: str, candidate: str) -> bool:
    """Loose match: equality, substring with word boundaries, or synonyms regex."""
    p = pantry_item
    c = candidate
    if not p or not c:
        return False
    if p == c:
        return True
    # word-boundary substring in either direction
    if re.search(rf"\b{re.escape(p)}\b", c):
        return True
    if re.search(rf"\b{re.escape(c)}\b", p):
        return True
    # synonyms
    for pat in SYNONYMS.get(p, []):
        if re.search(pat, c):
            return True
    return False

def _normalize_ingredient(name: str) -> str:
    """Normalize common typos/synonyms so the API matches better."""
    n = (name or "").strip().lower()
    fixes = {
        r"\bbell\s*peper\b": "bell pepper",
        r"\bsweet\s*corn\b": "corn",
        r"\bscallions?\b": "green onion",
    }
    for pat, repl in fixes.items():
        n = re.sub(pat, repl, n)
    return n


# ----------------------------
# Core pages & pantry CRUD
# ----------------------------
def home(request):
    return render(request, "core/home.html")

@login_required
def dashboard(request):
    ingredients = request.user.ingredients.all()
    form = IngredientForm()
    return render(
        request,
        "core/dashboard.html",
        {"ingredients": ingredients, "form": form},
    )

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
                logger.exception("Error saving ingredient")
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


# ----------------------------
# AI Recipes (OpenAI)
# ----------------------------
@login_required
def ai_recipes(request):
    # enforce POST for external calls (helps prevent crawlers from burning quota)
    if request.method != "POST":
        messages.error(request, "Use the button to generate AI recipes.")
        return redirect("dashboard")

    pantry = list(request.user.ingredients.values_list("name", flat=True))
    if not pantry:
        messages.warning(request, "Your pantry is empty. Add some ingredients first.")
        return redirect("dashboard")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        messages.error(request, "OpenAI API key not configured.")
        return redirect("dashboard")

    system_msg = (
        "You are a professional chef. Given pantry items, propose 4 dinner recipes. "
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
                "model": "gpt-4o-mini",
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
            logger.error("OpenAI non-200 response: %s %s", resp.status_code, resp.text)
            messages.error(request, f"AI request failed ({resp.status_code}).")
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


# ----------------------------
# Web Recipes (Spoonacular)
# ----------------------------
@login_required
def web_recipes(request):
    # enforce POST for external calls (helps prevent crawlers from burning quota)
    if request.method != "POST":
        messages.error(request, "Use the button to search recipes.")
        return redirect("dashboard")

    pantry_raw = list(request.user.ingredients.values_list("name", flat=True))
    pantry = [_normalize_ingredient(x) for x in pantry_raw if x and x.strip()]
    if not pantry:
        messages.warning(request, "Your pantry is empty.")
        return redirect("dashboard")

    api_key = os.getenv("SPOONACULAR_API_KEY")
    if not api_key:
        messages.error(request, "Spoonacular API key not set.")
        return redirect("dashboard")

    try:
        # 1) Find by ingredients
        find_url = "https://api.spoonacular.com/recipes/findByIngredients"
        find_resp = requests.get(
            find_url,
            params={
                "apiKey": api_key,
                "ingredients": ",".join(pantry),
                "number": 12,          # fetch a few more so we can filter
                "ranking": 2,          # maximize used ingredients
                "ignorePantry": True,  # ignore staples
                "fillIngredients": True,
            },
            timeout=20,
        )
        # handle quota
        if find_resp.status_code == 429:
            messages.error(request, "Spoonacular rate limit reached. Please try again later.")
            return redirect("dashboard")
        if find_resp.status_code != 200:
            logger.error("Spoonacular findByIngredients %s: %s", find_resp.status_code, find_resp.text)
            messages.error(request, f"Recipe search failed ({find_resp.status_code}).")
            return redirect("dashboard")

        found = find_resp.json() or []
        # First filter using Spoonacular's count
        found = [r for r in found if (r.get("usedIngredientCount") or 0) >= SPOON_MIN_MATCHED_API]
        if not found:
            messages.info(request, "No good matches—try adding one more ingredient.")
            return redirect("dashboard")

        ids = [str(item["id"]) for item in found if "id" in item][:9]
        if not ids:
            messages.info(request, "No good matches—try adding one more ingredient.")
            return redirect("dashboard")

        # 2) Enrich with details
        info_url = "https://api.spoonacular.com/recipes/informationBulk"
        info_resp = requests.get(
            info_url,
            params={"apiKey": api_key, "ids": ",".join(ids)},
            timeout=20,
        )
        if info_resp.status_code == 429:
            messages.error(request, "Spoonacular rate limit reached. Please try again later.")
            return redirect("dashboard")
        if info_resp.status_code != 200:
            logger.error("Spoonacular informationBulk %s: %s", info_resp.status_code, info_resp.text)
            messages.error(request, f"Recipe details failed ({info_resp.status_code}).")
            return redirect("dashboard")

        details = {str(d["id"]): d for d in info_resp.json() if "id" in d}

        # Filter out beverages
        EXCLUDE_TYPES = {"drink", "beverage", "beverages", "cocktail"}
        pantry_set = set(pantry)

        results = []
        for item in found:
            sid = str(item.get("id"))
            det = details.get(sid, {})
            dish_types = set((det.get("dishTypes") or []) + (det.get("occasions") or []))
            if dish_types & EXCLUDE_TYPES:
                continue

            # Build a reliable URL with fallbacks
            url = det.get("sourceUrl") or det.get("spoonacularSourceUrl")
            if not url and det.get("title") and sid:
                url = f"https://spoonacular.com/recipes/{slugify(det['title'])}-{sid}"

            # Normalize Spoonacular used/missed to compare against YOUR pantry (loosely)
            def norm(s): return (s or "").strip().lower()
            used_api = [norm(u.get("name")) for u in (item.get("usedIngredients") or [])]
            missed_api = [norm(m.get("name")) for m in (item.get("missedIngredients") or [])]

            # Confirm matches: pantry items that match ANY used_api ingredient
            used_confirmed = []
            for p in pantry:
                for cand in used_api:
                    if is_match(p, cand):
                        used_confirmed.append(p)
                        break
            used_confirmed = sorted(set(used_confirmed))

            # Missed list: keep Spoonacular’s view, but drop anything that actually matches our pantry (due to fuzzy logic)
            missed_clean = []
            for m in missed_api:
                if not any(is_match(p, m) for p in pantry):
                    missed_clean.append(m)
            missed_clean = sorted(set(missed_clean))

            # Require at least N confirmed matches
            if len(used_confirmed) < SPOON_MIN_CONFIRMED:
                continue


            results.append({
                "label": det.get("title") or item.get("title"),
                "image": det.get("image") or item.get("image"),
                "url": url,
                "readyInMinutes": det.get("readyInMinutes"),
                "servings": det.get("servings"),
                "usedIngredientCount": len(used_confirmed),
                "missedIngredientCount": len(missed_clean),
                "usedIngredients": used_confirmed,
                "missedIngredients": missed_clean,
            })

        if not results:
            messages.info(request, "No good matches. Try adding another ingredient or adjust filters.")
            return redirect("dashboard")

        return render(request, "core/web_results.html", {"results": results, "pantry": pantry})

    except requests.RequestException as e:
        logger.exception("Spoonacular network error")
        messages.error(request, f"Network error calling Spoonacular: {e}")
        return redirect("dashboard")
    except Exception as e:
        logger.exception("Spoonacular parsing error")
        messages.error(request, f"Unexpected error: {e}")
        return redirect("dashboard")

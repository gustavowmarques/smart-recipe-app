# ------------------------------------------------------------------------------
# Smart Recipe – Views
# Pantry → (AI recipes via OpenAI) and (Web recipes via Spoonacular)
# Includes "Favorites" (SavedRecipe) persistence using session-backed results.
#
# Key fixes in this version:
# - web_recipes(): assigns an integer `id` to each result AND stores results in session
#   (request.session["web_recipes"]) so recipe_detail() works for web results.
# - recipe_detail(): reads the proper session bucket based on source ("ai" or "web")
#   and shows a "Saved ✓" badge if already favorited.
# - save_favorite(): persists a recipe to SavedRecipe (dedup via get_or_create).
# - All relevant views protected with @login_required.
# ------------------------------------------------------------------------------

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import IngredientForm
from .models import Ingredient, SavedRecipe

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Tunable matching thresholds
# ------------------------------------------------------------------------------

# First filter: Spoonacular's own count of matched ingredients (API-side).
SPOON_MIN_MATCHED_API = 1  # keep results with >= this many matches (Spoonacular's view)

# Second filter: our own “confirmed” matches against the user pantry (loose).
SPOON_MIN_CONFIRMED = 1  # keep if at least this many loose matches are confirmed

# Dish types that imply “drink” in Spoonacular metadata
DRINK_TYPES = {"drink", "beverage", "beverages", "cocktail", "smoothie"}

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _fallback_image_from_spoonacular(title: str) -> str | None:
    """
    Try to find a representative image for an AI recipe by searching Spoonacular by title.
    Returns an image URL or None.
    """
    api_key = os.getenv("SPOONACULAR_API_KEY")
    if not api_key or not title:
        return None
    try:
        r = requests.get(
            "https://api.spoonacular.com/recipes/complexSearch",
            params={
                "apiKey": api_key,
                "query": title,
                "number": 1,
                "addRecipeInformation": True,  # ensures 'image' is present
            },
            timeout=12,
        )
        if r.status_code != 200:
            logger.warning("Spoonacular fallback image %s: %s", r.status_code, r.text[:200])
            return None
        items = (r.json() or {}).get("results") or []
        if not items:
            return None
        return items[0].get("image")
    except requests.RequestException:
        logger.exception("Spoonacular fallback image request failed")
        return None


def slugify(title: str) -> str:
    """URL-friendly slug for fall-back recipe links (e.g., spoonacular.com/recipes/<slug>-<id>)."""
    s = (title or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-") or "recipe"


# Loose matching helpers (to better align pantry vs API names).
SYNONYMS = {
    "beef": [
        r"\bbeef\b",
        r"\bground\s+beef\b",
        r"\bsirloin\b",
        r"\bsteak\b",
        r"\btop\s+round\b",
        r"\bchuck\b",
    ],
    "corn": [r"\bcorn\b", r"\bsweet\s+corn\b", r"\bcorn\s+on\s+the\s+cob\b", r"\bcorn\s+kernels?\b"],
    "bell pepper": [
        r"\bbell\s+pepper(s)?\b",
        r"\bred\s+pepper(s)?\b",
        r"\bgreen\s+pepper(s)?\b",
        r"\byellow\s+pepper(s)?\b",
        r"\bcapsicum\b",
    ],
}

def is_match(pantry_item: str, candidate: str) -> bool:
    """
    Loose ingredient matching:
    - Exact matches
    - Word-boundary substring matches in either direction
    - Simple synonym patterns for common items
    """
    p = (pantry_item or "").strip().lower()
    c = (candidate or "").strip().lower()
    if not p or not c:
        return False
    if p == c:
        return True
    if re.search(rf"\b{re.escape(p)}\b", c):
        return True
    if re.search(rf"\b{re.escape(c)}\b", p):
        return True
    for pat in SYNONYMS.get(p, []):
        if re.search(pat, c):
            return True
    return False


def _normalize_ingredient(name: str) -> str:
    """Light normalization to reduce variant names in the pantry."""
    n = (name or "").strip().lower()
    fixes = {
        r"\bbell\s*peper\b": "bell pepper",
        r"\bsweet\s*corn\b": "corn",
        r"\bscallions?\b": "green onion",
    }
    for pat, repl in fixes.items():
        n = re.sub(pat, repl, n)
    return n


def _get_session_recipe(source: str, recipe_id: int, request) -> Optional[dict]:
    """
    Look up a recipe dict by `id` from the appropriate session bucket.
    - source == "ai"  -> session["ai_recipes"]
    - source == "web" -> session["web_recipes"]
    """
    key = "ai_recipes" if source == "ai" else "web_recipes"
    recipes = request.session.get(key) or []
    for r in recipes:
        try:
            if int(r.get("id", -1)) == int(recipe_id):
                return r
        except Exception:
            # ignore malformed rows
            pass
    return None


# ------------------------------------------------------------------------------
# Core pages & pantry CRUD
# ------------------------------------------------------------------------------

def home(request):
    return render(request, "core/home.html")


@login_required
def dashboard(request):
    """Main app landing after login: pantry + calls to AI/Web."""
    ingredients = request.user.ingredients.all()
    form = IngredientForm()
    return render(request, "core/dashboard.html", {"ingredients": ingredients, "form": form})


@login_required
def add_ingredient(request):
    """Add a pantry ingredient for the current user."""
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
def delete_ingredient(request, pk: int):
    """Delete a pantry ingredient belonging to the current user."""
    ing = get_object_or_404(Ingredient, pk=pk, user=request.user)
    if request.method == "POST":
        ing.delete()
        messages.info(request, f"Removed {ing.name}.")
    return redirect("dashboard")


# ------------------------------------------------------------------------------
# AI Recipes (OpenAI) – returns 4 JSON recipes; optional AI images per recipe
# with a Spoonacular image fallback when AI images are disabled or blocked.
# ------------------------------------------------------------------------------

@login_required
def ai_recipes(request):
    if request.method != "POST":
        messages.error(request, "Use the button to generate AI recipes.")
        return redirect("dashboard")

    kind = (request.POST.get("kind") or "food").strip().lower()  # 'food' or 'drink'

    pantry = list(request.user.ingredients.values_list("name", flat=True))
    if not pantry:
        messages.warning(request, "Your pantry is empty. Add some ingredients first.")
        return redirect("dashboard")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        messages.error(request, "OpenAI API key not configured.")
        return redirect("dashboard")

    # Helper to generate an image URL with OpenAI Images (optional).
    # We keep it nested to avoid polluting the module with variants.
    def _gen_image_url(title: str, kind_: str) -> Optional[str]:
        try:
            prompt = (
                f"High-quality, appetizing {kind_} photo: {title}. "
                "Natural lighting, minimal props, social-ready composition."
            )
            r = requests.post(
                "https://api.openai.com/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-image-1",
                    "prompt": prompt,
                    # Valid sizes: "1024x1024", "1024x1536", "1536x1024", or "auto"
                    "size": "1024x1024",
                    "n": 1,
                },
                timeout=60,
            )
            if r.status_code == 403:
                # Some orgs/projects may not be verified for image gen: skip silently.
                logger.warning("OpenAI image gen blocked (403). Skipping images this run.")
                return None
            if r.status_code != 200:
                logger.error("OpenAI image gen %s: %s", r.status_code, r.text)
                return None

            payload = r.json()
            data = payload.get("data") or []
            return data[0].get("url") if data else None
        except requests.RequestException:
            logger.exception("Network error calling OpenAI Images")
            return None
        except Exception:
            logger.exception("Unexpected error parsing image response")
            return None

    # Fallback – try to fetch a representative image from Spoonacular by title
    def _fallback_image_from_spoonacular(title: str) -> Optional[str]:
        api_key_spoon = os.getenv("SPOONACULAR_API_KEY")
        if not api_key_spoon or not title:
            return None
        try:
            r = requests.get(
                "https://api.spoonacular.com/recipes/complexSearch",
                params={
                    "apiKey": api_key_spoon,
                    "query": title,
                    "number": 1,
                    "addRecipeInformation": True,  # ensures 'image' is present
                },
                timeout=12,
            )
            if r.status_code != 200:
                logger.warning("Spoonacular fallback image %s: %s", r.status_code, r.text[:200])
                return None
            items = (r.json() or {}).get("results") or []
            if not items:
                return None
            return items[0].get("image")
        except requests.RequestException:
            logger.exception("Spoonacular fallback image request failed")
            return None

    # Ask the model for STRICT JSON (4 recipes).
    system_msg = (
        "You are a professional chef. Generate exactly 4 recipes based on the user's pantry. "
        "Prefer using provided ingredients; suggest smart substitutions if needed. "
        f"The recipes must be type: {kind}. "
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
        payload = json.loads(data["choices"][0]["message"]["content"])
        recipes = (payload.get("recipes") or [])[:4]

        # Normalize + enrich + assign IDs + image (OpenAI first, then Spoonacular fallback)
        for idx, r in enumerate(recipes, start=1):
            r["id"] = idx  # IMPORTANT: used by recipe_detail() for lookup
            r["title"] = r.get("title") or f"Recipe {idx}"
            r["ingredients"] = r.get("ingredients") or []
            r["steps"] = r.get("steps") or []
            r["tags"] = r.get("tags") or []

            # Try OpenAI image first (only if enabled)
            r["image_url"] = _gen_image_url(r["title"], kind) if settings.ENABLE_AI_IMAGES else None

            # If no image (disabled or failed), try Spoonacular title search as a fallback
            if not r["image_url"]:
                r["image_url"] = _fallback_image_from_spoonacular(r["title"])

        # Store in session for detail page and saving to favorites
        request.session["ai_recipes"] = recipes
        request.session.modified = True

        return render(request, "core/ai_results.html", {"recipes": recipes, "pantry": pantry, "kind": kind})

    except requests.RequestException as e:
        logger.exception("Network error calling OpenAI")
        messages.error(request, f"Network error calling AI: {e}")
        return redirect("dashboard")
    except (KeyError, ValueError) as e:
        logger.exception("Failed to parse AI response")
        messages.error(request, f"Failed to parse AI response: {e}")
        return redirect("dashboard")


# ------------------------------------------------------------------------------
# Web Recipes (Spoonacular) – respects 'kind' ("food" vs "drink")
# Stores results in session with an integer 'id' so recipe_detail() works.
# ------------------------------------------------------------------------------

@login_required
def web_recipes(request):
    if request.method != "POST":
        messages.error(request, "Use the button to search recipes.")
        return redirect("dashboard")

    kind = (request.POST.get("kind") or "food").strip().lower()  # 'food' or 'drink'

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
        # (1) Find by ingredients
        find_resp = requests.get(
            "https://api.spoonacular.com/recipes/findByIngredients",
            params={
                "apiKey": api_key,
                "ingredients": ",".join(pantry),
                "number": 15,
                "ranking": 2,          # maximize used ingredients
                "ignorePantry": True,  # commonly available ingredients are ignored
                "fillIngredients": True,
            },
            timeout=20,
        )
        # Friendly handling of common Spoonacular errors
        if find_resp.status_code in (402, 429):
            try:
                detail = find_resp.json().get("message") or ""
            except Exception:
                detail = ""
            if find_resp.status_code == 402:
                msg = "Spoonacular daily points limit reached. Try again after reset or use AI recipes."
            else:  # 429
                msg = "Spoonacular rate limit reached. Please try again in a bit."
            if detail:
                msg += f" ({detail})"
            messages.error(request, msg)
            return redirect("dashboard")

        if find_resp.status_code != 200:
            logger.error("findByIngredients %s: %s", find_resp.status_code, find_resp.text)
            messages.error(request, f"Recipe search failed ({find_resp.status_code}).")
            return redirect("dashboard")


        found = [r for r in (find_resp.json() or []) if (r.get("usedIngredientCount") or 0) >= SPOON_MIN_MATCHED_API]
        if not found:
            messages.info(request, "No good matches—try adding one more ingredient.")
            return redirect("dashboard")

        ids = [str(item["id"]) for item in found if "id" in item][:12]
        if not ids:
            messages.info(request, "No good matches—try adding one more ingredient.")
            return redirect("dashboard")

        # (2) Enrich with bulk information
        info_resp = requests.get(
            "https://api.spoonacular.com/recipes/informationBulk",
            params={"apiKey": api_key, "ids": ",".join(ids)},
            timeout=20,
        )
        if info_resp.status_code == 429:
            messages.error(request, "Spoonacular rate limit reached. Please try again later.")
            return redirect("dashboard")
        if info_resp.status_code != 200:
            logger.error("informationBulk %s: %s", info_resp.status_code, info_resp.text)
            messages.error(request, f"Recipe details failed ({info_resp.status_code}).")
            return redirect("dashboard")

        details = {str(d["id"]): d for d in info_resp.json() if "id" in d}
        pantry_set = set(pantry)

        results: list[dict] = []
        for item in found:
            sid = str(item.get("id"))
            det = details.get(sid, {})
            dish_types = set((det.get("dishTypes") or []) + (det.get("occasions") or []))
            is_drink = bool(dish_types & DRINK_TYPES)

            # Respect the user choice:
            if kind == "food" and is_drink:
                continue
            if kind == "drink" and not is_drink:
                continue

            # Reliable URL
            url = det.get("sourceUrl") or det.get("spoonacularSourceUrl")
            if not url and det.get("title") and sid:
                url = f"https://spoonacular.com/recipes/{slugify(det['title'])}-{sid}"

            # Normalize candidate names from API
            def norm(s: Optional[str]) -> str:
                return (s or "").strip().lower()

            used_api = [norm(u.get("name")) for u in (item.get("usedIngredients") or [])]
            missed_api = [norm(m.get("name")) for m in (item.get("missedIngredients") or [])]

            # Confirmed matches (loose)
            used_confirmed = []
            for p in pantry:
                for cand in used_api:
                    if is_match(p, cand):
                        used_confirmed.append(p)
                        break
            used_confirmed = sorted(set(used_confirmed))

            # Missed that aren't really in pantry by loose match
            missed_clean = []
            for m in missed_api:
                if not any(is_match(p, m) for p in pantry):
                    missed_clean.append(m)
            missed_clean = sorted(set(missed_clean))

            if len(used_confirmed) < SPOON_MIN_CONFIRMED:
                continue

            # Build ingredients (prefer Spoonacular extendedIngredients)
            ingredients_full = det.get("extendedIngredients") or []
            # Extract steps: prefer analyzedInstructions → steps[].step; fallback to plain instructions
            steps_list = []
            an = det.get("analyzedInstructions") or []
            if isinstance(an, list) and an and isinstance(an[0], dict):
                steps_list = [s.get("step") for s in (an[0].get("steps") or []) if s.get("step")]
            if not steps_list and det.get("instructions"):
                steps_list = [s.strip() for s in det["instructions"].split("\n") if s.strip()]

            title = det.get("title") or item.get("title")

            results.append(
                {
                    "id": int(sid),                               # <- IMPORTANT for detail lookup
                    "title": title,                               # <- use 'title' (your template reads recipe.title)
                    "label": title,                               # <- keep label for backwards compatibility
                    "image": det.get("image") or item.get("image"),
                    "url": url,
                    "readyInMinutes": det.get("readyInMinutes"),
                    "servings": det.get("servings"),
                    "usedIngredientCount": len(used_confirmed),
                    "missedIngredientCount": len(missed_clean),
                    "usedIngredients": used_confirmed,
                    "missedIngredients": missed_clean,
                    # NEW: include full data so detail page has content and Save captures it
                    "ingredients": ingredients_full,
                    "steps": steps_list,
                    # also include Spoonacular’s original list if you want to use it in Save
                    "extendedIngredients": ingredients_full,
                    "instructions": "\n".join(steps_list) if steps_list else det.get("instructions", ""),
                }
            )

        if not results:
            messages.info(request, "No good matches. Try adding another ingredient or adjust filters.")
            return redirect("dashboard")

        # Store in session so recipe_detail(web) can find items by id
        request.session["web_recipes"] = results
        request.session.modified = True

        return render(request, "core/web_results.html", {"results": results, "pantry": pantry, "kind": kind})

    except requests.RequestException as e:
        logger.exception("Spoonacular network error")
        messages.error(request, f"Network error calling Spoonacular: {e}")
        return redirect("dashboard")
    except Exception as e:
        logger.exception("Spoonacular parsing error")
        messages.error(request, f"Unexpected error: {e}")
        return redirect("dashboard")


# ------------------------------------------------------------------------------
# Recipe detail & Favorites
# ------------------------------------------------------------------------------

@login_required
def recipe_detail(request, recipe_id: int, source: str = "ai"):
    """
    Show details for a recipe that exists in the session bucket:
      - source="ai":  session["ai_recipes"]
      - source="web": session["web_recipes"]
    Falls back to the other bucket if not found (for convenience).
    """
    recipe = _get_session_recipe(source, recipe_id, request)
    if not recipe:
        other = "web" if source == "ai" else "ai"
        recipe = _get_session_recipe(other, recipe_id, request)
        source = other if recipe else source
    if not recipe:
        raise Http404("Recipe not found in session results.")

    # Check if already saved
    external_id = str(recipe.get("id", "")) if source == "web" else str(recipe.get("id", recipe_id))
    already = SavedRecipe.objects.filter(
        user=request.user, source=source, external_id=external_id
    ).exists()

    return render(request, "core/recipe_detail.html", {"recipe": recipe, "source": source, "already_saved": already})

@login_required
def favorite_detail(request, pk: int):
    """
    Render a saved recipe straight from the database, without relying on
    session data. We build a 'recipe' dict shaped like the one used by
    recipe_detail.html so we can reuse that template.
    """
    fav = get_object_or_404(SavedRecipe, pk=pk, user=request.user)

    # Normalize data so recipe_detail.html can render consistently
    ingredients = fav.ingredients_json or []
    steps = fav.steps_json or []

    # Build a dict that looks like the session-based object
    recipe = {
        "id": fav.external_id or fav.pk,      # not used for saving here (already saved)
        "title": fav.title or "Recipe",
        "image_url": fav.image_url or "",
        "ingredients": ingredients,            # may be list[str] or list[dict] with 'original'
        "extendedIngredients": ingredients,    # fallback path in template
        "steps": steps if isinstance(steps, list) else [],
        "instructions": (
            "\n".join(steps) if isinstance(steps, list) else (steps or "")
        ),
        # Web-only hints (empty here; not needed but keeps template happy)
        "usedIngredients": [],
        "missedIngredients": [],
        "readyInMinutes": None,
        "servings": None,
        # Optional: if you later store a source URL on SavedRecipe, pass it here as "url"
        # "url": fav.source_url,
    }

    # Reuse the existing detail template; force 'already_saved' so the Save button is hidden
    return render(
        request,
        "core/recipe_detail.html",
        {"recipe": recipe, "source": fav.source, "already_saved": True},
    )

@login_required
@require_POST
def save_favorite(request, source: str, recipe_id: int):
    """
    Save a session-backed recipe to the user's favorites.
    For web recipes, external_id is the Spoonacular ID.
    For AI recipes, we reuse the session `id` as a stable key for the run.
    """
    recipe = _get_session_recipe(source, recipe_id, request)
    if not recipe:
        messages.error(request, "Recipe no longer available to save.")
        return redirect("dashboard")

    external_id = str(recipe.get("id", "")) if source == "web" else str(recipe.get("id", recipe_id))
    title = recipe.get("title") or recipe.get("name") or "Untitled"
    image_url = recipe.get("image_url") or recipe.get("image") or ""

    # Normalize ingredients & steps from either AI or Web payloads
    ingredients = recipe.get("ingredients") or recipe.get("extendedIngredients") or []
    if ingredients and isinstance(ingredients[0], dict):
        # Spoonacular’s extendedIngredients
        ingredients = [i.get("original") or i.get("name") for i in ingredients]

    steps = recipe.get("steps") or recipe.get("instructions") or []
    if isinstance(steps, str):
        steps = [s.strip() for s in steps.split("\n") if s.strip()]

    _, created = SavedRecipe.objects.get_or_create(
        user=request.user,
        source=source,
        external_id=external_id,
        defaults={
            "title": title[:200],
            "image_url": image_url,
            "ingredients_json": ingredients,
            "steps_json": steps,
        },
    )
    if created:
        messages.success(request, "Saved to Favorites.")
    else:
        messages.info(request, "Already in your Favorites.")

    return redirect("recipe_detail_ai" if source == "ai" else "recipe_detail_web", recipe_id=recipe_id)


@login_required
def favorites_list(request):
    """List favorites for the current user."""
    items = request.user.saved_recipes.all()
    return render(request, "core/favorites.html", {"items": items})


@login_required
@require_POST
def favorite_delete(request, pk: int):
    """Remove a favorite belonging to the current user."""
    fav = get_object_or_404(SavedRecipe, pk=pk, user=request.user)
    fav.delete()
    messages.success(request, "Removed from Favorites.")
    return redirect("favorites")

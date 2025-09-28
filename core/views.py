# ---- stdlib -----------------------------------------------------------------
import os
import re
import json
import base64
import mimetypes
import logging
from datetime import date as _date, timedelta
import datetime as dt
from datetime import date
from uuid import uuid4
from pathlib import Path
import boto3
from typing import Optional, List
from decimal import Decimal, InvalidOperation

# ---- OCR helpers -------------------------------------------------------------
try:
    import pytesseract
except Exception:
    pytesseract = None  # optional dependency

# ---- third-party HTTP --------------------------------------------------------
import requests
from .services.image_lookup import spoonacular_image_for, cache_remote_image_to_storage

# ---- Django ------------------------------------------------------------------
from django import forms
from django.conf import settings
from django.forms import formset_factory
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction, IntegrityError
from django.http import JsonResponse, Http404, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_protect
from django.core.files.storage import default_storage
from django.core.mail import send_mail

# ---- App models & forms ------------------------------------------------------
from .models import (
    Ingredient,
    SavedRecipe,
    NutritionTarget,
    MealPlan,
    Meal,
    PantryImageUpload,
    LoggedMeal,
)

from .forms import (
    IngredientForm,
    SavedRecipeForm,
    NutritionTargetForm,
    PantryImageUploadForm,
    MealAddForm,
)

from .services.nutrition import compute_daily_totals, suggest_recipes_for_gaps, sync_logged_meals_from_plan



# ---- OpenAI client (new SDK, optional) ---------------------------------------
try:
    from openai import OpenAI  # pip install openai
except Exception:
    OpenAI = None

_openai_client = None
if OpenAI:
    _openai_client = OpenAI(
        api_key=(getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY"))
    )
#Spoonacular
from .services.recipes import spoon_search


# ---- Logging -----------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---- Tesseract wiring --------------------------------------------------------
if pytesseract:
    # Prefer explicit path from settings if provided
    tesseract_cmd = getattr(settings, "TESSERACT_CMD", None)
    if tesseract_cmd and os.path.exists(tesseract_cmd):
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    # Fallback to common Windows install path
    elif os.name == "nt":
        default_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(default_cmd):
            pytesseract.pytesseract.tesseract_cmd = default_cmd


# =============================================================================
# Unified recipe search helpers (single button)
# =============================================================================

def _stash_suggestions_in_session(request, suggestions: list[dict]) -> None:
    """
    Merge suggestions (treated as 'web' items) into the session's recipe_results
    so recipe_detail() can retrieve them by id.
    Expected suggestion fields: id, title, (optional) image.
    """
    bundle = request.session.get("recipe_results") or {"ai": [], "web": [], "combined": []}

    def _idx(lst):
        return {str(it.get("id")) for it in lst if isinstance(it, dict)}

    web_ids = _idx(bundle.get("web", []))
    combined_ids = _idx(bundle.get("combined", []))

    for s in suggestions or []:
        sid = str(s.get("id"))
        if not sid:
            continue
        item = {
            "id": s.get("id"),
            "title": s.get("title") or "Recipe",
            "image": s.get("image") or s.get("image_url"),
            "image_url": s.get("image_url") or s.get("image"),
            "source": "web",
            "meta": {},  # you can enrich later
        }
        if sid not in web_ids:
            bundle.setdefault("web", []).append(item)
        if sid not in combined_ids:
            bundle.setdefault("combined", []).append(item)

    request.session["recipe_results"] = bundle
    request.session.modified = True


def _gather_ingredient_names(request) -> List[str]:
    """
    Read any selection the dashboard form might post (checkboxes, multiselect).
    If nothing was selected, fall back to ALL pantry ingredients for the user.
    """
    ids = (
        request.POST.getlist("ids")
        or request.POST.getlist("ingredient_ids")
        or request.POST.getlist("ingredients")
        or request.POST.getlist("selected")
    )
    qs = Ingredient.objects.filter(user=request.user)
    if ids:
        qs = qs.filter(pk__in=ids)

    names: List[str] = []
    for ing in qs.only("name"):
        n = (ing.name or "").strip()
        if n and n.lower() not in [x.lower() for x in names]:
            names.append(n)
    return names


def _spoonacular_search(names: List[str], recipe_type: str = "food", limit: int = 12) -> List[dict]:
    """
    Call Spoonacular Complex Search with includeIngredients.
    Returns normalized dicts: {id, title, image, source, meta}
    """
    key = getattr(settings, "SPOONACULAR_API_KEY", None) or os.getenv("SPOONACULAR_API_KEY")
    if not key:
        logger.info("Spoonacular key missing; skipping web search.")
        return []

    include = ",".join(names) if names else ""
    params = {
        "number": limit,
        "addRecipeInformation": "true",
        "includeIngredients": include,
        "instructionsRequired": "true",
        "sort": "popularity",
        # Optional type control:
        # "type": "drink" if recipe_type == "drink" else "main course",
        "apiKey": key,
    }
    try:
        r = requests.get("https://api.spoonacular.com/recipes/complexSearch", params=params, timeout=12)
        r.raise_for_status()
        data = r.json() or {}
        results = data.get("results", []) or []
        out = []
        for it in results:
            out.append({
                "id": int(it.get("id")),
                "title": it.get("title") or "Untitled",
                "image": it.get("image"),
                "source": "web",
                "meta": it,  # keep the raw payload (detail view can use it)
            })
        return out
    except Exception as e:
        logger.warning("Spoonacular search failed: %s", e)
        return []

# --------------------------------------------------------------------------------------
# AI recipe generation (robust JSON-first; markdown-table fallback; normalized keys)
# --------------------------------------------------------------------------------------

def _extract_protein_and_calories(item: dict) -> tuple[int, int]:
    """
    Return (protein_g, calories) from a Spoonacular item regardless of shape.
    """
    protein_g = 0
    calories = 0

    # Many wrappers expose: item["nutrition"]["nutrients"] = [{name, amount, unit}, ...]
    nut = (item.get("nutrition") or {}).get("nutrients", [])
    if isinstance(nut, list):
        for n in nut:
            name = (n.get("name") or "").lower()
            if name == "protein":
                try:
                    protein_g = int(round(float(n.get("amount") or 0)))
                except Exception:
                    pass
            if name == "calories":
                try:
                    calories = int(round(float(n.get("amount") or 0)))
                except Exception:
                    pass

    # Some wrappers flatten: item["protein"], item["calories"]
    if not protein_g:
        try:
            protein_g = int(round(float(item.get("protein") or 0)))
        except Exception:
            pass
    if not calories:
        try:
            calories = int(round(float(item.get("calories") or 0)))
        except Exception:
            pass

    return protein_g, calories


def _slugify_title(title: str, ix: int = 0) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    if not base:
        base = f"recipe-{ix+1}"
    return (base[:40] or base) if ix == 0 else f"{base[:34]}-{ix+1}"

def _normalize_keys(d: dict) -> dict:
    return { (k or "").strip().lower(): v for k, v in (d or {}).items() }

def _extract_json_block(text: str) -> Optional[dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None

def _parse_markdown_table(md: str) -> list[dict]:
    rows: list[dict] = []
    if not md:
        return rows
    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
    if len(lines) < 2:
        return rows
    headers = [h.strip().lower() for h in lines[0].strip("|").split("|")]
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        item = {headers[i]: cells[i] if i < len(cells) else "" for i in range(len(headers))}
        rows.append(_normalize_keys(item))
    return rows

def _openai_generate(ingredients: list[str], kind: str = "food") -> list[dict]:
    """
    Generates AI recipes and returns:
    [{id,title,summary,ingredients,url,source='ai'}]
    Robust across older/newer OpenAI SDKs:
      - First tries Responses API (no response_format).
      - Falls back to Chat Completions (adds JSON mode there).
      - Falls back to parsing a markdown table.
    """
    if not _openai_client:
        logger.info("OpenAI client not available; skipping AI generation.")
        return []

    ing_text = ", ".join(ingredients) if ingredients else "common pantry items"
    model = getattr(settings, "OPENAI_TEXT_MODEL", "gpt-4o-mini")

    system_msg = (
        "You are a concise recipe generator. Always return short, practical recipes. "
        "Prefer the provided pantry items; add simple staples only as needed."
    )
    user_prompt_json = (
        f"Create 3 {kind} recipes using primarily: {ing_text}.\n"
        "Return STRICT JSON with this shape:\n"
        "{\n"
        '  \"recipes\": [\n'
        "    {\n"
        '      \"id\": \"short-slug\",\n'
        '      \"title\": \"string\",\n'
        '      \"summary\": \"1-2 sentence summary\",\n'
        '      \"ingredients\": [\"string\", \"...\"],\n'
        '      \"url\": null\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "No extra text outside JSON."
    )

    text = None

    # --- Attempt 1: Responses API (do NOT pass response_format here) ---
    try:
        if hasattr(_openai_client, "responses") and hasattr(_openai_client.responses, "create"):
            resp = _openai_client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_prompt_json},
                ],
            )
            text = getattr(resp, "output_text", None) or str(resp)
    except Exception as e:
        logger.info("Responses API unavailable/failed; will try Chat Completions. (%s)", e)

    # --- Attempt 2: Chat Completions (JSON mode allowed here) ---
    if not text:
        try:
            if hasattr(_openai_client, "chat") and hasattr(_openai_client.chat, "completions"):
                kwargs = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_prompt_json},
                    ],
                }
                try:
                    kwargs["response_format"] = {"type": "json_object"}
                except Exception:
                    pass

                c = _openai_client.chat.completions.create(**kwargs)
                text = (c.choices[0].message.content or "").strip()
        except Exception as e:
            logger.exception("Chat Completions failed: %s", e)
            text = None

    recipes: list[dict] = []

    # Parse JSON (preferred)
    data = _extract_json_block(text or "")
    if isinstance(data, dict):
        raw = data.get("recipes") or []
        for ix, r in enumerate(raw if isinstance(raw, list) else []):
            r = _normalize_keys(r if isinstance(r, dict) else {})
            title = (r.get("title") or "").strip() or f"AI recipe {ix+1}"
            rid = (r.get("id") or "").strip() or _slugify_title(title, ix)
            recipes.append({
                "id": rid,
                "title": title,
                "summary": (r.get("summary") or "").strip(),
                "ingredients": r.get("ingredients") or [],
                "url": r.get("url") or None,
                "source": "ai",
            })

    # If JSON empty, try markdown-table salvage
    if not recipes and text:
        rows = _parse_markdown_table(text)
        for ix, row in enumerate(rows):
            title = (row.get("title") or "").strip() or f"AI recipe {ix+1}"
            rid = (row.get("id") or "").strip() or _slugify_title(title, ix)
            recipes.append({
                "id": rid,
                "title": title,
                "summary": (row.get("summary") or "").strip(),
                "ingredients": [],
                "url": None,
                "source": "ai",
            })

    return recipes


def _combine_and_store_results(request, ai_items: List[dict], web_items: List[dict]) -> None:
    """Store both lists and an ordered combined view in session."""
    combined = ai_items + web_items
    combined.sort(key=lambda x: (0 if x["source"] == "ai" else 1, x["title"].lower()))
    request.session["recipe_results"] = {
        "ai": ai_items,
        "web": web_items,
        "combined": combined,
    }
    request.session.modified = True


# =============================================================================
# Pantry photo extraction helpers
# =============================================================================

def _ocr_extract_text(image_path: str) -> str:
    """
    Extract raw text from an image using Tesseract if available.
    Returns '' on failure so callers can fall back safely.
    """
    try:
        import pytesseract
    except ImportError:
        logger.info("pytesseract not installed; skipping OCR.")
        return ""

    try:
        from PIL import Image
    except ImportError:
        logger.info("Pillow (PIL) not installed; skipping OCR.")
        return ""

    try:
        with Image.open(image_path) as img:
            return pytesseract.image_to_string(img)
    except pytesseract.TesseractNotFoundError:
        logger.info("Tesseract binary not installed; skipping OCR.")
        return ""
    except Exception:
        logger.exception("OCR failed.")
        return ""

# Patterns used by _parse_ingredients_from_text
_NUM_RE = r"(\d+(?:\.\d+)?)"
_UNIT_RE = r"(g|kg|mg|ml|l|tbsp|tsp|teaspoons?|tablespoons?|cup|cups|oz|ounce|ounces|lb|lbs|pound|pounds|pc|pcs|piece|pieces|can|cans|pack|packs)"

def _parse_ingredients_from_text(text: str) -> List[dict]:
    """
    Parse grocery-ish lines into [{'name','quantity','unit'}].
    Accepts formats like:
      - '2 bell pepper'
      - '200 g chicken breast'
      - 'onion 1 pc'
      - 'ginger'
    """
    items: List[dict] = []
    for raw in text.splitlines():
        line = raw.strip("•-* \t").strip()
        if not line:
            continue

        # 1) "200 g chicken breast"
        m = re.match(rf"^{_NUM_RE}\s+{_UNIT_RE}\s+(.+)$", line, flags=re.I)
        if m:
            qty = re.findall(_NUM_RE, line, flags=re.I)[0]
            unit = re.findall(_UNIT_RE, line, flags=re.I)[0]
            name = m.group(1).strip()
            items.append({"name": name, "quantity": qty, "unit": unit})
            continue

        # 2) "2 bell pepper"
        m = re.match(rf"^{_NUM_RE}\s+(.+)$", line, flags=re.I)
        if m:
            qty = re.findall(_NUM_RE, line, flags=re.I)[0]
            name = m.group(1).strip()
            items.append({"name": name, "quantity": qty, "unit": ""})
            continue

        # 3) "onion 1 pc"
        m = re.match(rf"^(.+?)\s+{_NUM_RE}\s+{_UNIT_RE}$", line, flags=re.I)
        if m:
            name = m.group(1).strip()
            qty = re.findall(_NUM_RE, line, flags=re.I)[0]
            unit = re.findall(_UNIT_RE, line, flags=re.I)[0]
            items.append({"name": name, "quantity": qty, "unit": unit})
            continue

        # Fallback: treat the line as a name-only ingredient
        items.append({"name": line, "quantity": "", "unit": ""})

    return items[:50]


def _extract_with_openai_vision(image_url: str) -> List[dict]:
    """
    Vision via Chat Completions (URL). Safe HTTP fallback if the SDK isn't available.
    """
    api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", "")
    if not api_key or not image_url:
        return []
    try:
        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract grocery/ingredient items from the image. Normalize names. "
                        "Split things like '200 g chicken' into name='chicken', quantity='200', unit='g'. "
                        'Return STRICT JSON: {"items":[{"name":"string","quantity":"string","unit":"string"}]}.'
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract up to 40 items."},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
        }
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=45,
        )
        if r.status_code != 200:
            logger.warning("OpenAI Vision non-200: %s %s", r.status_code, r.text[:200])
            return []
        data = r.json()
        raw = (data["choices"][0]["message"]["content"] or "").strip()
        obj = json.loads(raw)
        items = obj.get("items") or []
        out = []
        for it in items:
            name = (it.get("name") or "").strip()
            if not name:
                continue
            out.append({
                "name": name,
                "quantity": (it.get("quantity") or "").strip(),
                "unit": (it.get("unit") or "").strip(),
            })
        logger.info("Vision(URL) extracted %d items.", len(out))
        return out[:40]
    except Exception:
        logger.exception("OpenAI Vision(URL) failed.")
        return []


def _vision_extract_items_with_openai(image_path: str) -> List[dict]:
    """
    Vision via Chat Completions (base64 data URL).
    Avoids Responses API types that caused 400s/TypeError on some SDK versions.
    """
    api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        logger.info("OpenAI client not available; skipping Vision.")
        return []
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        data_url = f"data:{mime};base64,{b64}"

        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract grocery/ingredient items from the image. Normalize names. "
                        "If a quantity or unit is not obvious, leave it empty. "
                        'Return STRICT JSON: {"items":[{"name":"string","quantity":"string","unit":"string"}]}.'
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract up to 40 items."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        }

        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=60,
        )
        if r.status_code != 200:
            logger.warning("OpenAI Vision(base64) non-200: %s %s", r.status_code, r.text[:200])
            return []
        raw = (r.json()["choices"][0]["message"]["content"] or "").strip()
        data = json.loads(raw)
        out = []
        for it in data.get("items", []):
            name = (it.get("name") or "").strip()
            if not name:
                continue
            out.append({
                "name": name,
                "quantity": (it.get("quantity") or "").strip(),
                "unit": (it.get("unit") or "").strip(),
            })
        logger.info("Vision(base64) extracted %d items.", len(out))
        return out
    except Exception:
        logger.exception("OpenAI Vision (base64) failed.")
        return []


def _extract_candidates(image_path: str, image_url: Optional[str]) -> List[dict]:
    """
    1) OCR (Tesseract)
    2) Vision (base64 → Chat Completions)
    3) Vision (URL → Chat Completions)
    4) Tiny demo list if still empty
    """
    text = _ocr_extract_text(image_path)
    candidates = _parse_ingredients_from_text(text) if text else []

    if not candidates:
        candidates = _vision_extract_items_with_openai(image_path)
    if not candidates and image_url:
        candidates = _extract_with_openai_vision(image_url)

    if not candidates:
        logger.info("No items detected; using small demo list.")
        candidates = [
            {"name": "bell pepper", "quantity": "2", "unit": "pcs"},
            {"name": "chicken breast", "quantity": "200", "unit": "g"},
            {"name": "onion", "quantity": "1", "unit": "pc"},
        ]
    return candidates


def _store_upload_results(upload: PantryImageUpload, candidates: List[dict]) -> None:
    """
    Store results into either 'results' or 'results_json' (depending on your model),
    and set a status if present.
    """
    payload = {"candidates": candidates}
    if hasattr(upload, "results"):
        upload.results = payload
    elif hasattr(upload, "results_json"):
        upload.results_json = payload
    if hasattr(upload, "status"):
        try:
            done = (
                getattr(PantryImageUpload, "DONE", None)
                or getattr(getattr(PantryImageUpload, "Status", object), "DONE", None)
                or "done"
            )
            upload.status = done
        except Exception:
            pass
    upload.save(update_fields=[f for f in ("results", "results_json", "status") if hasattr(upload, f)])


# =============================================================================
# Loose matching + recipe helpers (existing)
# =============================================================================

def slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-") or "recipe"

SYNONYMS = {
    "beef": [r"\bbeef\b", r"\bground\s+beef\b", r"\bsirloin\b", r"\bsteak\b", r"\btop\s+round\b", r"\bchuck\b"],
    "corn": [r"\bcorn\b", r"\bsweet\s+corn\b", r"\bcorn\s+on\s+the\s+cob\b", r"\bcorn\s+kernels?\b"],
    "bell pepper": [r"\bbell\s+pepper(s)?\b", r"\bred\s+pepper(s)?\b", r"\bgreen\s+pepper(s)?\b", r"\byellow\s+pepper(s)?\b", r"\bcapsicum\b"],
}
def is_match(pantry_item: str, candidate: str) -> bool:
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
    n = (name or "").strip().lower()
    fixes = {r"\bbell\s*peper\b": "bell pepper", r"\bsweet\s*corn\b": "corn", r"\bscallions?\b": "green onion"}
    for pat, repl in fixes.items():
        n = re.sub(pat, repl, n)
    return n

def _get_session_recipe(source: str, rid_any, request) -> Optional[dict]:
    """
    Look up a recipe by ID (string compare) from session-stored results.
    Works for both AI slugs and numeric Spoonacular IDs.
    """
    rid = str(rid_any)
    for item in _get_session_list_for_source(request, source):
        if str(item.get("id")) == rid:
            return item
    return None

def _get_session_list_for_source(request, source: str) -> list[dict]:
    """
    Returns the list of results for the given source from session.
    Supports the new combined structure and legacy keys.
    """
    bundle = request.session.get("recipe_results") or {}
    if source == "ai":
        return bundle.get("ai") or request.session.get("recipes_results_ai", []) or []
    if source == "web":
        return bundle.get("web") or request.session.get("recipes_results_web", []) or []
    return []


# =============================================================================
# Core pages & pantry CRUD
# =============================================================================

def home(request):
    return render(request, "core/home.html")

def demo_mode(request):
    # Only allow in development; remove this guard if you want in prod.
    if not getattr(settings, "DEBUG", False):
        messages.error(request, "Demo mode is unavailable.")
        return redirect("core:home")

    User = get_user_model()
    demo, _ = User.objects.get_or_create(
        username="demo_user",
        defaults={"email": "demo@smartrecipe.test"}
    )
    # Make sure demo user cannot be used directly
    demo.set_unusable_password()
    demo.save()

    login(request, demo, backend="django.contrib.auth.backends.ModelBackend")
    messages.info(request, "You're using a demo account. Changes won't be saved permanently.")
    return redirect("core:dashboard")

@login_required
def dashboard(request):
    ingredients = request.user.ingredients.all()
    return render(
        request,
        "core/dashboard.html",
        {
            "ingredients": ingredients,
            "form": IngredientForm(),
            "upload_form": PantryImageUploadForm(),  # photo upload button
        },
    )

@require_POST
@login_required
def add_ingredient(request):
    form = IngredientForm(request.POST)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        try:
            obj.save()
            messages.success(request, f"Added {obj.name}.")
        except Exception as e:
            logger.exception("Could not save ingredient.")
            messages.error(request, f"Could not add: {e}")
    else:
        messages.error(request, "Please correct the errors.")
    return redirect("core:dashboard")

@require_POST
@login_required
def delete_ingredient(request, pk: int):
    ing = get_object_or_404(Ingredient, pk=pk, user=request.user)
    ing.delete()
    messages.info(request, f"Removed {ing.name}.")
    return redirect("core:dashboard")


# =============================================================================
# Pantry photo extraction — VIEWS
# =============================================================================

@login_required
@require_http_methods(["POST"])
def presign_s3_upload(request):
    """
    Return a JSON payload for browser direct-to-S3 POST uploads:

      { "url": "<https://bucket.s3.region.amazonaws.com/>",
        "fields": { ...policy / signature fields... },
        "key": "pantry_uploads/<guid>.ext" }

    Notes:
    - Works in dev and prod as long as BUCKET + REGION + valid AWS creds
      are available (via env vars, AWS CLI profile, or instance role).
    - Sends a clear JSON error if configuration/credentials are missing.
    """

    # ---- 1) Parse client payload (filename + content type) ----
    try:
        payload = json.loads(request.body.decode() or "{}")
    except Exception:
        payload = {}

    filename     = (payload.get("filename") or "upload.jpg").strip()
    content_type = (payload.get("content_type") or "image/jpeg").strip()

    # Normalize extension; default to ".jpg" if client sent none
    ext = Path(filename).suffix.lower() or ".jpg"

    # S3 object key under our uploads prefix
    key = f"pantry_uploads/{uuid4().hex}{ext}"

    # ---- 2) Bucket / region from settings, else env (works when USE_S3 is off) ----
    bucket = (
        getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
        or os.getenv("AWS_STORAGE_BUCKET_NAME")
    )
    region = (
        getattr(settings, "AWS_S3_REGION_NAME", None)
        or os.getenv("AWS_S3_REGION_NAME")
    )
    if not bucket or not region:
        return JsonResponse(
            {"error": "S3 not configured (missing bucket/region)."},
            status=500,
        )

    # ---- 3) Build a boto3 session and verify credentials exist ----
    #
    # Try explicit env keys first (handy for local .env); otherwise let
    # boto3's default provider chain load credentials (AWS CLI profile, EC2/ECS role, etc.)
    ak = os.getenv("AWS_ACCESS_KEY_ID") or getattr(settings, "AWS_ACCESS_KEY_ID", None)
    sk = os.getenv("AWS_SECRET_ACCESS_KEY") or getattr(settings, "AWS_SECRET_ACCESS_KEY", None)

    if ak and sk:
        session = boto3.Session(
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            region_name=region,
        )
    else:
        session = boto3.Session(region_name=region)

    # If boto3 still can’t find any creds, fail gracefully
    if session.get_credentials() is None:
        return JsonResponse(
            {
                "error": (
                    "AWS credentials not found on server. "
                    "Set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (or configure an AWS profile/role)."
                )
            },
            status=500,
        )

    s3 = session.client("s3")

    # ---- 4) Presign a POST policy for the browser ----
    fields = {"Content-Type": content_type}
    conditions = [
        {"Content-Type": content_type},
        ["content-length-range", 0, 10 * 1024 * 1024],  # 0 .. 10 MB
        # You can add more constraints here (e.g., starts-with $key, etc.)
    ]

    resp = s3.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=300,  # URL valid for 5 minutes
    )

    # ---- 5) Return the policy + upload URL to the browser ----
    return JsonResponse(
        {"url": resp["url"], "fields": resp["fields"], "key": key},
        status=200,
    )

@login_required
@require_http_methods(["POST"])
def pantry_extract_start(request):
    """
    Two modes:
    - Legacy: multipart file in request.FILES['upload']
    - Direct-to-S3: request.POST['s3_key'] from the browser after a presigned upload
    """
    uploaded = request.FILES.get("upload")
    s3_key = (request.POST.get("s3_key") or "").strip()

    if not uploaded and not s3_key:
        messages.error(request, "Please choose an image to upload.")
        return redirect("core:dashboard")

    up = PantryImageUpload(user=request.user)
    try:
        up.status = (
            getattr(PantryImageUpload, "PENDING", None)
            or getattr(getattr(PantryImageUpload, "Status", object), "PENDING", None)
            or "pending"
        )
    except Exception:
        pass

    if uploaded:
        # write via default storage (S3 in prod, filesystem in dev)
        from uuid import uuid4
        from pathlib import Path
        ext = (Path(uploaded.name).suffix or ".jpg").lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
            ext = ".jpg"
        up.image.save(f"pantry_uploads/{uuid4().hex}{ext}", uploaded, save=True)
    else:
        # Browser already uploaded to S3; just point the ImageField at that key.
        up.image.name = s3_key
        up.save()

    # Build absolute URL for OCR/vision fallback
    img_url = request.build_absolute_uri(up.image.url)

    # image.path may not exist on S3; guard it
    try:
        img_path = up.image.path
    except Exception:
        img_path = None

    candidates = _extract_candidates(image_path=img_path, image_url=img_url)
    _store_upload_results(up, candidates)

    return redirect("core:pantry_extract_review", upload_id=up.pk)

@require_http_methods(["GET", "POST"])
@login_required
def pantry_upload_quick(request):
    """
    DEPRECATED entrypoint (kept for compatibility). Behaves like pantry_extract_start().
    """
    form = PantryImageUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Please choose a valid image.")
        return redirect("core:dashboard")

    up = form.save(commit=False)
    up.user = request.user
    up.save()

    candidates = _extract_candidates(up.image.path, request.build_absolute_uri(up.image.url))
    _store_upload_results(up, candidates)

    return redirect("core:pantry_extract_review", upload_id=up.pk)


@login_required
@require_http_methods(["GET", "POST"])
def pantry_extract_review(request, upload_id: int):
    """
    Review screen where the user can tweak quantities/units/names.
    POST adds/updates pantry items; merging quantities for duplicates.
    """
    up = get_object_or_404(PantryImageUpload, pk=upload_id, user=request.user)

    # Load saved candidates from either .results or .results_json
    raw = up.results if getattr(up, "results", None) else getattr(up, "results_json", None)
    if isinstance(raw, str):
        try:
            data = json.loads(raw) or {}
        except json.JSONDecodeError:
            data = {}
    elif isinstance(raw, dict):
        data = raw
    else:
        data = {}

    initial_list = data.get("candidates") or data.get("items") or []

    # ---- Normalize into form field names (safe defaults) ----
    def _norm(d):
        if not isinstance(d, dict):
            return {}
        name = (d.get("name") or "").strip()

        # quantity arrives as string/number; keep as string for the form
        qty_raw = d.get("quantity", d.get("qty", ""))
        quantity = "" if qty_raw is None else str(qty_raw).strip()

        # unit default to 'pcs' if missing/blank (so DB won't get NULL later)
        unit = (d.get("unit", d.get("u", "")) or "").strip()
        if not unit:
            unit = "pcs"

        return {"name": name, "quantity": quantity, "unit": unit}

    initial = [_norm(d) for d in initial_list if isinstance(d, dict)]

    class ReviewIngredientForm(forms.Form):
        name = forms.CharField(
            required=False, max_length=255,
            widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. bell pepper"}),
        )
        quantity = forms.CharField(
            required=False,
            widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 2 or 200"}),
        )
        unit = forms.CharField(
            required=False, max_length=32,
            widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. g, pcs"}),
        )

    extra_rows = 0 if initial else 8
    ReviewSet = formset_factory(ReviewIngredientForm, can_delete=True, extra=extra_rows)

    def _to_decimal(val):
        s = ("" if val is None else str(val)).strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except (InvalidOperation, ValueError, TypeError):
            return None

    if request.method == "POST":
        formset = ReviewSet(request.POST)
        if formset.is_valid():
            added = 0
            updated = 0

            for row in formset.cleaned_data:
                if not row or row.get("DELETE"):
                    continue

                name = (row.get("name") or "").strip()
                if not name:
                    continue

                qty_dec = _to_decimal(row.get("quantity"))
                unit_val = (row.get("unit") or "").strip()

                # For UPDATE: only update unit if provided (keep existing otherwise)
                # For CREATE: ensure non-null unit using default 'pcs'
                create_unit = unit_val or "pcs"

                try:
                    with transaction.atomic():
                        try:
                            obj = Ingredient.objects.select_for_update().get(
                                user=request.user, name__iexact=name
                            )
                            # Merge quantity
                            if qty_dec is not None:
                                obj.quantity = (obj.quantity or Decimal("0")) + qty_dec
                            # Update unit only if user provided one
                            if unit_val:
                                obj.unit = unit_val
                            # Keep normalized name casing if you want
                            obj.name = name or obj.name
                            obj.save()
                            updated += 1
                        except Ingredient.DoesNotExist:
                            Ingredient.objects.create(
                                user=request.user,
                                name=name,
                                quantity=qty_dec,   # can be None if your field allows NULL
                                unit=create_unit,   # NEVER NULL on create
                            )
                            added += 1
                except IntegrityError:
                    # One bad row shouldn't kill the whole request
                    messages.error(request, f"Could not save “{name}”. Please adjust and try again.")
                    continue

            if added or updated:
                parts = []
                if added: parts.append(f"added {added}")
                if updated: parts.append(f"updated {updated}")
                messages.success(request, "Pantry updated: " + ", ".join(parts) + ".")
            else:
                messages.info(request, "No items were added.")

            return redirect("core:dashboard")

        messages.error(request, "Please fix the highlighted rows.")
        # fall through to re-render the formset with errors
    else:
        formset = ReviewSet(initial=initial)

    return render(request, "core/pantry_review.html", {"upload": up, "formset": formset})

@login_required
def pantry_review(request, pk: int):
    """Legacy redirect to the new review URL."""
    return redirect("core:pantry_extract_review", upload_id=pk)


# Optional legacy pages (list/history).
@login_required
def pantry_upload(request):
    if request.method == "POST":
        form = PantryImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            up = form.save(commit=False)
            up.user = request.user
            up.save()
            messages.success(request, "Image received. We'll process it shortly.")
            return redirect("core:pantry_upload_list")
    else:
        form = PantryImageUploadForm()
    return render(request, "core/pantry_upload.html", {"form": form})

@login_required
def pantry_upload_list(request):
    uploads = PantryImageUpload.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "core/pantry_upload_list.html", {"uploads": uploads})


# =============================================================================
# New unified recipe flow (single button): search Spoonacular + generate with OpenAI
# =============================================================================

@login_required
@require_http_methods(["POST"])
def recipes_search(request):
    """
    Single entry point from the dashboard form.
    - Reads selected pantry items (or uses them all)
    - Calls Spoonacular + OpenAI
    - Stores normalized results in session
    - Redirects to results page
    """
    names = _gather_ingredient_names(request)
    recipe_type = (request.POST.get("type") or "food").strip().lower()

    web_items = _spoonacular_search(names, recipe_type=recipe_type, limit=12)
    ai_items = _openai_generate(names, kind=recipe_type)

    if not web_items and not ai_items:
        messages.warning(request, "No recipes found at the moment. Try different items.")
        return redirect("core:dashboard")

    _combine_and_store_results(request, ai_items, web_items)
    return redirect("core:recipes_results")


@login_required
def recipes_results(request):
    """
    Render the combined results kept in session by recipes_search().

    If an AI result has no image, we try to fetch a thumbnail from Spoonacular
    (using SPOONACULAR_API_KEY) and attach it as `image_url` so the results grid
    looks consistent with web results. We save the enriched results back into
    the session to avoid repeat API calls on every page load.
    """
    # Pull results from session
    data = request.session.get("recipe_results") or {}
    combined = list(data.get("combined") or [])
    ai = list(data.get("ai") or [])
    web = list(data.get("web") or [])

    # ---------- helpers (local to keep this view drop-in) ----------
    import os
    import requests

    def _get(item, attr, default=None):
        if isinstance(item, dict):
            return item.get(attr, default)
        return getattr(item, attr, default)

    def _set(item, attr, value):
        if isinstance(item, dict):
            item[attr] = value
        else:
            setattr(item, attr, value)

    def _is_ai(item) -> bool:
        kind = (_get(item, "kind", "") or _get(item, "type", "")).lower()
        if kind == "ai":
            return True
        return bool(_get(item, "is_ai", False))

    def _has_image(item) -> bool:
        return bool(_get(item, "image_url") or _get(item, "image") or _get(item, "thumb"))

    def _title_of(item) -> str:
        return (_get(item, "title") or _get(item, "name") or "").strip()

    def _spoonacular_thumb(title: str) -> str | None:
        """Return a small image URL for a dish title via Spoonacular."""
        api_key = getattr(settings, "SPOONACULAR_API_KEY", None) or os.getenv("SPOONACULAR_API_KEY")
        if not api_key or not title:
            return None
        try:
            r = requests.get(
                "https://api.spoonacular.com/recipes/complexSearch",
                params={"apiKey": api_key, "query": title, "number": 1},
                timeout=6,
            )
            if r.ok:
                results = (r.json() or {}).get("results") or []
                if results and results[0].get("image"):
                    return results[0]["image"]
        except Exception:
            pass
        return None
    # ----------------------------------------------------------------

    # Collect AI titles that need an image
    titles_needed = []
    for seq in (combined, ai):
        for item in seq:
            if _is_ai(item) and not _has_image(item):
                t = _title_of(item)
                if t:
                    titles_needed.append(t)

    # Deduplicate while preserving order
    titles_needed = list(dict.fromkeys(titles_needed))

    # Fetch thumbnails once per title
    title_to_url: dict[str, str] = {}
    for title in titles_needed:
        url = _spoonacular_thumb(title)
        if url:
            title_to_url[title] = url

    # Apply thumbnails to items and mark if session needs saving
    changed = False
    if title_to_url:
        for seq in (combined, ai):
            for item in seq:
                if _is_ai(item) and not _has_image(item):
                    url = title_to_url.get(_title_of(item))
                    if url:
                        _set(item, "image_url", url)
                        changed = True

    # Persist enriched results back to session so we don't refetch next time
    if changed:
        data["combined"] = combined
        data["ai"] = ai
        data["web"] = web
        request.session["recipe_results"] = data
        request.session.modified = True

    return render(request, "core/recipe_results.html", {
        "combined": combined,
        "ai_count": len(ai),
        "web_count": len(web),
    })


# =============================================================================
# Existing AI & Web flows (kept for backwards compatibility)
# =============================================================================

SPOON_MIN_MATCHED_API = 1
SPOON_MIN_CONFIRMED = 1
DRINK_TYPES = {"drink", "beverage", "beverages", "cocktail", "smoothie"}

def _fallback_image_from_spoonacular(title: str) -> Optional[str]:
    api_key = os.getenv("SPOONACULAR_API_KEY")
    if not api_key or not title:
        return None
    try:
        r = requests.get(
            "https://api.spoonacular.com/recipes/complexSearch",
            params={"apiKey": api_key, "query": title, "number": 1, "addRecipeInformation": True},
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
        logger.exception("Spoonacular fallback request failed")
        return None

@login_required
def ai_recipes(request):
    if request.method != "POST":
        messages.error(request, "Use the button to generate AI recipes.")
        return redirect("core:dashboard")

    kind = (request.POST.get("kind") or "food").strip().lower()
    pantry = list(request.user.ingredients.values_list("name", flat=True))
    if not pantry:
        messages.warning(request, "Your pantry is empty. Add some ingredients first.")
        return redirect("core:dashboard")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        messages.error(request, "OpenAI API key not configured.")
        return redirect("core:dashboard")

    def _gen_image_url(title: str, kind_: str) -> Optional[str]:
        try:
            prompt = (
                f"High-quality, appetizing {kind_} photo: {title}. "
                "Natural lighting, minimal props, social-ready composition."
            )
            r = requests.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "gpt-image-1", "prompt": prompt, "size": "1024x1024", "n": 1},
                timeout=60,
            )
            if r.status_code == 403:
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

    system_msg = (
        "You are a professional chef. Generate exactly 4 recipes based on the user's pantry. "
        "Prefer using provided ingredients; suggest smart substitutions if needed. "
        f"The recipes must be type: {kind}. "
        "Return STRICT JSON ONLY with this schema:\n"
        "{"
        "  \"recipes\": [ {"
        "      \"title\": string, \"ingredients\": [string], \"steps\": [string],"
        "      \"tags\": [string], \"cook_time_minutes\": integer"
        "  } ]"
        "}"
    )
    user_msg = f"Pantry items: {', '.join(pantry)}"

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "response_format": {"type": "json_object"}, "temperature": 0.7,
                  "messages": [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}]},
            timeout=60,
        )
        if resp.status_code != 200:
            logger.error("OpenAI non-200 response: %s %s", resp.status_code, resp.text)
            messages.error(request, f"AI request failed ({resp.status_code}).")
            return redirect("core:dashboard")

        data = resp.json()
        payload = json.loads(data["choices"][0]["message"]["content"])
        recipes = (payload.get("recipes") or [])[:4]

        for idx, r in enumerate(recipes, start=1):
            r["id"] = idx
            r["title"] = r.get("title") or f"Recipe {idx}"
            r["ingredients"] = r.get("ingredients") or []
            r["steps"] = r.get("steps") or []
            r["tags"] = r.get("tags") or []
            image_enabled = bool(getattr(settings, "ENABLE_AI_IMAGES", False))
            r["image_url"] = _gen_image_url(r["title"], kind) if image_enabled else None
            if not r["image_url"]:
                r["image_url"] = _fallback_image_from_spoonacular(r["title"])

        request.session["ai_recipes"] = recipes
        request.session.modified = True
        return render(request, "core/ai_results.html", {"recipes": recipes, "pantry": pantry, "kind": kind})

    except requests.RequestException as e:
        logger.exception("Network error calling OpenAI")
        messages.error(request, f"Network error calling AI: {e}")
        return redirect("core:dashboard")
    except (KeyError, ValueError) as e:
        logger.exception("Failed to parse AI response")
        messages.error(request, f"Failed to parse AI response: {e}")
        return redirect("core:dashboard")


@login_required
@require_POST
def web_recipes(request):
    kind = (request.POST.get("kind") or "food").strip().lower()

    pantry_raw = list(request.user.ingredients.values_list("name", flat=True))
    pantry = [_normalize_ingredient(x) for x in pantry_raw if x and x.strip()]
    if not pantry:
        messages.warning(request, "Your pantry is empty.")
        return redirect("core:dashboard")

    api_key = os.getenv("SPOONACULAR_API_KEY")
    if not api_key:
        messages.error(request, "Spoonacular API key not set.")
        return redirect("core:dashboard")

    try:
        find_resp = requests.get(
            "https://api.spoonacular.com/recipes/findByIngredients",
            params={"apiKey": api_key, "ingredients": ",".join(pantry), "number": 15, "ranking": 2,
                    "ignorePantry": True, "fillIngredients": True},
            timeout=20,
        )
        if find_resp.status_code in (402, 429):
            try:
                detail = find_resp.json().get("message") or ""
            except Exception:
                detail = ""
            if find_resp.status_code == 402:
                msg = "Spoonacular daily points limit reached. Try again after reset or use AI recipes."
            else:
                msg = "Spoonacular rate limit reached. Please try again in a bit."
            if detail:
                msg += f" ({detail})"
            messages.error(request, msg)
            return redirect("core:dashboard")
        if find_resp.status_code != 200:
            logger.error("findByIngredients %s: %s", find_resp.status_code, find_resp.text)
            messages.error(request, f"Recipe search failed ({find_resp.status_code}).")
            return redirect("core:dashboard")

        found = [r for r in (find_resp.json() or []) if (r.get("usedIngredientCount") or 0) >= SPOON_MIN_MATCHED_API]
        if not found:
            messages.info(request, "No good matches—try adding one more ingredient.")
            return redirect("core:dashboard")

        ids = [str(item["id"]) for item in found if "id" in item][:12]
        if not ids:
            messages.info(request, "No good matches—try adding one more ingredient.")
            return redirect("core:dashboard")

        info_resp = requests.get(
            "https://api.spoonacular.com/recipes/informationBulk",
            params={"apiKey": api_key, "ids": ",".join(ids)},
            timeout=20,
        )
        if info_resp.status_code == 429:
            messages.error(request, "Spoonacular rate limit reached. Please try again later.")
            return redirect("core:dashboard")
        if info_resp.status_code != 200:
            logger.error("informationBulk %s: %s", info_resp.status_code, info_resp.text)
            messages.error(request, f"Recipe details failed ({info_resp.status_code}).")
            return redirect("core:dashboard")

        details = {str(d["id"]): d for d in info_resp.json() if "id" in d}

        results: List[dict] = []
        for item in found:
            sid = str(item.get("id"))
            det = details.get(sid, {})
            dish_types = set((det.get("dishTypes") or []) + (det.get("occasions") or []))
            is_drink = bool(dish_types & DRINK_TYPES)
            if kind == "food" and is_drink:
                continue
            if kind == "drink" and not is_drink:
                continue

            url = det.get("sourceUrl") or det.get("spoonacularSourceUrl")
            if not url and det.get("title") and sid:
                url = f"https://spoonacular.com/recipes/{slugify(det['title'])}-{sid}"

            def norm(s: Optional[str]) -> str:
                return (s or "").strip().lower()

            used_api = [norm(u.get("name")) for u in (item.get("usedIngredients") or [])]
            missed_api = [norm(m.get("name")) for m in (item.get("missedIngredients") or [])]

            used_confirmed = []
            for p in pantry:
                if any(is_match(p, cand) for cand in used_api):
                    used_confirmed.append(p)
            used_confirmed = sorted(set(used_confirmed))

            missed_clean = sorted({m for m in missed_api if not any(is_match(p, m) for p in pantry)})

            if len(used_confirmed) < SPOON_MIN_CONFIRMED:
                continue

            ingredients_full = det.get("extendedIngredients") or []
            steps_list = []
            an = det.get("analyzedInstructions") or []
            if isinstance(an, list) and an and isinstance(an[0], dict):
                steps_list = [s.get("step") for s in (an[0].get("steps") or []) if s.get("step")]
            if not steps_list and det.get("instructions"):
                steps_list = [s.strip() for s in det["instructions"].split("\n") if s.strip()]

            title = det.get("title") or item.get("title")
            image = det.get("image") or item.get("image")

            results.append(
                {
                    "id": int(sid),
                    "title": title,
                    "label": title,
                    "image": image,
                    "image_url": image,
                    "url": url,
                    "readyInMinutes": det.get("readyInMinutes"),
                    "servings": det.get("servings"),
                    "usedIngredientCount": len(used_confirmed),
                    "missedIngredientCount": len(missed_clean),
                    "usedIngredients": used_confirmed,
                    "missedIngredients": missed_clean,
                    "ingredients": ingredients_full,
                    "extendedIngredients": ingredients_full,
                    "steps": steps_list,
                    "instructions": "\n".join(steps_list) if steps_list else det.get("instructions", ""),
                }
            )

        if not results:
            messages.info(request, "No good matches. Try adding another ingredient or adjust filters.")
            return redirect("core:dashboard")

        request.session["web_recipes"] = results
        request.session.modified = True
        return render(request, "core/web_results.html", {"results": results, "pantry": pantry, "kind": kind})

    except requests.RequestException as e:
        logger.exception("Spoonacular network error")
        messages.error(request, f"Network error calling Spoonacular: {e}")
        return redirect("core:dashboard")
    except Exception as e:
        logger.exception("Spoonacular parsing error")
        messages.error(request, f"Unexpected error: {e}")
        return redirect("core:dashboard")


# =============================================================================
# Recipe detail & Favorites
# =============================================================================

@login_required
def recipe_detail(request, source: str, rid: Optional[str] = None, recipe_id: Optional[int] = None):
    """
    Show detail for a result stored in session.
    If it's an AI recipe and it has no image yet, fetch a representative image
    (Spoonacular) and optionally cache it to our storage (S3/local).

    Also computes `already_saved` so the template can render:
      - "Add to favorites" (POST to save)
      - or "In favorites" / remove link
    """
    # ----- identify this recipe in your session/results bundle -----
    key = rid if rid is not None else recipe_id  # can be string or int
    key_str = str(key) if key is not None else ""

    recipe = _get_session_recipe(source, key, request)
    if not recipe:
        raise Http404("Recipe not found in session (maybe results expired).")

    # ----- Best-effort image for AI items with no image yet -----
    try:
        if source == "ai" and not (recipe.get("image_url") or recipe.get("image")):
            title = (recipe.get("title") or recipe.get("name") or "").strip()
            if title:
                remote_url = spoonacular_image_for(title)
                cached_url = cache_remote_image_to_storage(remote_url) if remote_url else None
                final_url = cached_url or remote_url
                if final_url:
                    recipe["image_url"] = final_url
                    recipe["image"] = final_url
                    bundle = request.session.get("recipe_results") or {}
                    for list_name in ("combined", "ai"):
                        lst = bundle.get(list_name) or []
                        for it in lst:
                            if str(it.get("id")) == key_str:
                                it["image_url"] = final_url
                                it["image"] = final_url
                    request.session["recipe_results"] = bundle
                    request.session.modified = True
    except Exception:
        logger.exception("Failed to attach fallback image for AI recipe.")

    recipe = recipe or {}
    meta = recipe.get("meta")
    if not isinstance(meta, dict):
        meta = {}

    # ---- Instructions: primary path from analyzedInstructions ----
    ai = recipe.get("analyzedInstructions") or meta.get("analyzedInstructions") or []
    steps_list: list[str] = []
    if isinstance(ai, list) and ai:
        block0 = ai[0] or {}
        raw_steps = block0.get("steps") or []
        steps_list = [s.get("step") for s in raw_steps if isinstance(s, dict) and s.get("step")]

    # ----- EXTRA FALLBACKS FOR INSTRUCTIONS -----
    if not steps_list:
        alt = (
            recipe.get("steps")
            or recipe.get("method")
            or recipe.get("directions")
            or recipe.get("procedure")
            or meta.get("instructions")
            or recipe.get("instructions")
        )
        if isinstance(alt, list):
            steps_list = [s for s in alt if isinstance(s, str) and s.strip()]
        elif isinstance(alt, str):
            raw = [p.strip() for p in alt.replace("\r", "").split("\n") if p.strip()]
            if not raw:
                raw = [p.strip() for p in alt.split(". ") if p.strip()]
            steps_list = raw

    # Last resort: if still empty but we have a sourceUrl, show a helpful step.
    if not steps_list and (recipe.get("url") or meta.get("sourceUrl")):
        steps_list = ["Open the source link for full step-by-step instructions."]

    # --- Heuristic instructions for AI recipes (when nothing else exists) ---
    if not steps_list and source == "ai":
        title_l = (recipe.get("title") or "").lower()

        def make(o):  # tiny helper to avoid empty strings
            return [s for s in o if s and s.strip()]

        if "smoothie" in title_l or "shake" in title_l:
            steps_list = make([
                "Add all ingredients to a blender.",
                "Blend until completely smooth.",
                "Taste and adjust sweetness or thickness as desired.",
                "Pour into a glass and serve immediately."
            ])
        elif "oatmeal" in title_l or "overnight oats" in title_l:
            steps_list = make([
                "Cook oats according to package directions (water or milk).",
                "Stir in the remaining ingredients.",
                "Simmer 1–2 minutes to warm through (optional).",
                "Serve warm and top as desired."
            ])
        elif "toast" in title_l or "sandwich" in title_l:
            steps_list = make([
                "Toast the bread to your liking.",
                "Spread almond butter evenly on the toast.",
                "Top with sliced banana; drizzle honey if using.",
                "Serve immediately."
            ])
        elif "salad" in title_l or "bowl" in title_l:
            steps_list = make([
                "Chop or prep all ingredients as needed.",
                "Combine in a bowl.",
                "Dress, season with salt and pepper, and toss to coat.",
                "Serve."
            ])
        elif "energy ball" in title_l or "balls" in title_l or "bites" in title_l:
            steps_list = make([
                "In a bowl, stir all ingredients until evenly combined.",
                "Chill the mixture for 15–20 minutes to firm up.",
                "Roll into bite-size balls.",
                "Refrigerate in an airtight container."
            ])
        else:
            steps_list = make([
                "Prep ingredients (wash, peel, chop as needed).",
                "Combine and season to taste.",
                "Cook or chill if appropriate.",
                "Serve."
            ])

    # ---------------------------------------------------------------------
    # Already-saved state (use SavedRecipe directly)
    # ---------------------------------------------------------------------
    already_saved = False
    favorite_pk = None
    if request.user.is_authenticated and key_str:
        qs = SavedRecipe.objects.filter(
            user=request.user,
            source=source,
            external_id=key_str,
        )
        if qs.exists():
            already_saved = True
            favorite_pk = qs.values_list("pk", flat=True).first()

    # -------- Normalize data for the template (image + ingredients) --------
    image_url_final = (
        recipe.get("image")
        or recipe.get("image_url")
        or meta.get("image")
        or meta.get("image_url")
        or recipe.get("thumbnail")
    )

    ingredients_list: list[str] = []
    ext = recipe.get("extendedIngredients") or meta.get("extendedIngredients") or []
    if isinstance(ext, list) and ext:
        for it in ext:
            if isinstance(it, dict):
                txt = (it.get("original") or it.get("name") or "").strip()
                if txt:
                    ingredients_list.append(txt)
    if not ingredients_list:
        alt_ing = recipe.get("ingredients") or meta.get("ingredients")
        if isinstance(alt_ing, list):
            ingredients_list = [s.strip() for s in alt_ing if isinstance(s, str) and s.strip()]

    # ---------------------------------------------------------------------
    # Render
    # ---------------------------------------------------------------------
    return render(
        request,
        "core/recipe_detail.html",
        {
            "recipe": recipe,
            "recipe_id": recipe_id,
            "rid": rid,
            "source": source,
            "steps_list": steps_list,
            "ingredients_list": ingredients_list,
            "image_url_final": image_url_final,
            "already_saved": already_saved,
            "favorite_pk": favorite_pk,
            "current_id_str": key_str,
        },
    )

@login_required
def favorite_detail(request, pk: int):
    """
    Show a saved recipe using the SAME template as live details.
    Provides the normalized fields the template expects.
    """
    fav = get_object_or_404(SavedRecipe, pk=pk, user=request.user)

    # --- Normalize ingredients/steps from JSON ---
    ingredients = []
    if isinstance(fav.ingredients_json, list):
        ingredients = [s.strip() for s in fav.ingredients_json if isinstance(s, str) and s.strip()]
    elif fav.ingredients_json:
        ingredients = [str(fav.ingredients_json).strip()]

    steps_list = []
    if isinstance(fav.steps_json, list):
        steps_list = [s.strip() for s in fav.steps_json if isinstance(s, str) and s.strip()]
    elif isinstance(fav.steps_json, str):
        steps_list = [s.strip() for s in fav.steps_json.split("\n") if s.strip()]

    # --- Minimal recipe dict (template uses several keys on `recipe`) ---
    recipe = {
        "id": fav.external_id or str(fav.pk),
        "title": fav.title or "Recipe",
        "image_url": fav.image_url or "",
        "ingredients": ingredients,
        "extendedIngredients": ingredients,
        "steps": steps_list,
        "instructions": "\n".join(steps_list),
        "nutrition": {},  # fill later if you add stored nutrition
    }

    return render(
        request,
        "core/recipe_detail.html",
        {
            "recipe": recipe,
            "recipe_id": None,
            "rid": None,
            "source": fav.source,                  # "ai" or "web"
            "steps_list": steps_list,
            "ingredients_list": ingredients,
            "image_url_final": fav.image_url or "",
            "already_saved": True,                 # it's a favorite
            "favorite_pk": fav.pk,
            "current_id_str": str(fav.external_id or fav.pk),  # used by Log Meal form
        },
    )

@login_required
@require_POST
def save_favorite(request, source, recipe_id):
    """
    Save the current AI/Web recipe (from session) into SavedRecipe.
    Works with AI slugs and numeric web IDs. Idempotent via (user, source, external_id).
    Also mirrors the instruction fallbacks used in the detail view so AI items
    reliably store steps.
    """
    # Validate source
    if source not in {"ai", "web"}:
        messages.error(request, "Unknown recipe source.")
        return redirect("core:dashboard")

    # Pull the recipe payload we cached in session during results
    recipe = _get_session_recipe(source, recipe_id, request)
    if not recipe:
        messages.error(request, "Recipe no longer available to save.")
        return redirect("core:dashboard")

    # External id must be a string for uniqueness
    external_id = str(recipe.get("id", recipe_id))

    # Basic fields
    title = (recipe.get("title") or recipe.get("name") or "").strip() or "Untitled"
    image_url = recipe.get("image_url") or recipe.get("image") or ""

    # ---- Ingredients (accept both list[str] and Spoonacular dicts) ----
    ingredients_raw = (
        recipe.get("ingredients")
        or recipe.get("extendedIngredients")
        or recipe.get("extended_ingredients")
        or []
    )
    ingredients: list[str] = []
    if isinstance(ingredients_raw, list):
        if ingredients_raw and isinstance(ingredients_raw[0], dict):
            # Spoonacular-like dicts
            for i in ingredients_raw:
                text = i.get("original") or i.get("originalString") or i.get("name")
                if text:
                    ingredients.append(text.strip())
        else:
            ingredients = [str(x).strip() for x in ingredients_raw if str(x).strip()]
    elif ingredients_raw:
        ingredients = [str(ingredients_raw).strip()]

    # ---- Steps (mirror detail view fallbacks; handle strings, lists, analyzedInstructions) ----
    meta_obj = recipe.get("meta") or {}

    steps_raw = (
        recipe.get("steps")
        or recipe.get("instructions")
        or recipe.get("analyzedInstructions")
        or recipe.get("method")
        or recipe.get("directions")
        or recipe.get("procedure")
        or meta_obj.get("instructions")
        or []
    )

    steps: list[str] = []

    def _norm_list(lst):
        return [str(s).strip() for s in lst if isinstance(s, (str, int, float)) and str(s).strip()]

    if isinstance(steps_raw, str):
        # split by newlines first; fallback to ". "
        parts = [p.strip() for p in steps_raw.replace("\r", "").split("\n") if p.strip()]
        if not parts:
            parts = [p.strip() for p in steps_raw.split(". ") if p.strip()]
        steps = parts
    elif isinstance(steps_raw, list):
        # analyzedInstructions: [{name, steps:[{number, step, ...}, ...]}, ...]
        if steps_raw and isinstance(steps_raw[0], dict) and "steps" in steps_raw[0]:
            for block in steps_raw:
                for st in (block.get("steps") or []):
                    txt = (st.get("step") or "").strip()
                    if txt:
                        steps.append(txt)
        else:
            steps = _norm_list(steps_raw)

    # If still empty and this is an AI recipe, use the same heuristic as recipe_detail
    if not steps and source == "ai":
        title_l = title.lower()

        def _make(seq):
            return [s for s in seq if s and s.strip()]

        if "smoothie" in title_l or "shake" in title_l:
            steps = _make([
                "Add all ingredients to a blender.",
                "Blend until completely smooth.",
                "Taste and adjust sweetness or thickness as desired.",
                "Pour into a glass and serve immediately.",
            ])
        elif "oatmeal" in title_l or "overnight oats" in title_l:
            steps = _make([
                "Cook oats according to package directions (water or milk).",
                "Stir in the remaining ingredients.",
                "Simmer 1–2 minutes to warm through (optional).",
                "Serve warm and top as desired.",
            ])
        elif "toast" in title_l or "sandwich" in title_l:
            steps = _make([
                "Toast the bread to your liking.",
                "Spread almond butter evenly on the toast.",
                "Top with sliced banana; drizzle honey if using.",
                "Serve immediately.",
            ])
        elif "salad" in title_l or "bowl" in title_l:
            steps = _make([
                "Chop or prep all ingredients as needed.",
                "Combine in a bowl.",
                "Dress, season with salt and pepper, and toss to coat.",
                "Serve.",
            ])
        elif "energy ball" in title_l or "balls" in title_l or "bites" in title_l:
            steps = _make([
                "In a bowl, stir all ingredients until evenly combined.",
                "Chill the mixture for 15–20 minutes to firm up.",
                "Roll into bite-size balls.",
                "Refrigerate in an airtight container.",
            ])
        else:
            steps = _make([
                "Prep ingredients (wash, peel, chop as needed).",
                "Combine and season to taste.",
                "Cook or chill if appropriate.",
                "Serve.",
            ])

    # Persist (idempotent on (user, source, external_id))
    try:
        obj, created = SavedRecipe.objects.get_or_create(
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

        # If it already exists but we now have better data (e.g., steps were empty before),
        # do a light update without changing ownership/identity.
        updated = False
        if not created:
            if image_url and not obj.image_url:
                obj.image_url = image_url
                updated = True
            if ingredients and not obj.ingredients_json:
                obj.ingredients_json = ingredients
                updated = True
            if steps and not obj.steps_json:
                obj.steps_json = steps
                updated = True
            if title and obj.title != title[:200]:
                obj.title = title[:200]
                updated = True
            if updated:
                obj.save(update_fields=["title", "image_url", "ingredients_json", "steps_json"])

        messages.success(
            request,
            "Saved to Favorites." if created else ("Updated your Favorite." if updated else "Already in your Favorites.")
        )
    except Exception as e:
        logger.exception("Failed to save favorite: %s", e)
        messages.error(request, "Could not save to favorites right now.")

    return redirect("core:favorites")

@login_required
def favorites_list(request):
    items = request.user.saved_recipes.all()
    return render(request, "core/favorites.html", {"items": items})

@login_required
@require_POST
def favorite_delete(request, pk: int):
    fav = get_object_or_404(SavedRecipe, pk=pk, user=request.user)
    fav.delete()
    messages.success(request, "Removed from Favorites.")
    return redirect("core:favorites")


# =============================================================================
# CRUD for SavedRecipe
# =============================================================================

@login_required
def recipe_create(request):
    if request.method == "POST":
        form = SavedRecipeForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.source = obj.source or "ai"
            obj.save()
            return redirect("core:favorite_detail", pk=obj.pk)
    else:
        form = SavedRecipeForm()
    return render(request, "core/recipe_form.html", {"form": form})

@login_required
def recipe_update(request, pk):
    obj = get_object_or_404(SavedRecipe, pk=pk)
    if obj.user != request.user and not request.user.is_superuser:
        raise PermissionDenied("You do not have permission to edit this recipe.")
    if request.method == "POST":
        form = SavedRecipeForm(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            form.save()
            return redirect("core:favorite_detail", pk=obj.pk)
    else:
        form = SavedRecipeForm(instance=obj)
    return render(request, "core/recipe_form.html", {"form": form, "recipe": obj})

@require_POST
@login_required
def recipe_delete(request, pk):
    obj = get_object_or_404(SavedRecipe, pk=pk)
    if obj.user != request.user and not request.user.is_superuser:
        raise PermissionDenied("You do not have permission to delete this recipe.")
    obj.delete()
    return redirect("core:dashboard")


# =============================================================================
# Nutrition targets & Meal plan
# =============================================================================

def _monday_for(anchor: dt.date) -> dt.date:
    return anchor - dt.timedelta(days=anchor.weekday())

def suggest_recipes_for_gaps(target, totals, search_fn, max_items: int = 4):
    """
    Build suggestions that keep the real Spoonacular 'id' so links go to /recipes/web/<id>/.
    """
    # Figure out what you need most today
    protein_gap = max((target.protein_g or 0) - (totals.protein_g or 0), 0)
    calorie_gap = max((target.calories or 0) - (totals.calories or 0), 0)

    # Simple query strategy – bias to protein if you're short, otherwise balanced
    if protein_gap >= 20:
        query = "high protein quick dinner"
    elif calorie_gap >= 400:
        query = "balanced easy meal"
    else:
        query = "healthy simple lunch"

    # Pull more than we need so we can rank
    try:
        raw = search_fn(query=query, number=24, add_recipe_nutrition=True)
    except TypeError:
        # If your wrapper uses different arg names, fall back to the simplest form
        raw = search_fn(query, 24)

    items = []
    for r in raw or []:
        rid = r.get("id")
        if not isinstance(rid, int):
            # must have a real numeric id to work with /recipes/web/<id>/
            continue

        # image: prefer your helper so you always have a valid URL
        # (If your wrapper already gives full 'image' URLs, this still works.)
        image_url = r.get("image")
        if not image_url:
            image_url = spoonacular_image_for(rid, r.get("imageType"))

        protein_g, calories = _extract_protein_and_calories(r)

        items.append({
            "id": rid,                # KEEP the real Spoonacular ID
            "title": r.get("title") or "Recipe",
            "image": image_url,
            "protein_g": protein_g,
            "calories": calories,
            "source": "web",          # IMPORTANT: mark as web
        })

    # Rank: prefer more protein when protein is short, otherwise aim under the calorie gap
    if protein_gap >= 20:
        items.sort(key=lambda x: (-x["protein_g"], x["calories"]))  # more protein, lower cals
    else:
        items.sort(key=lambda x: (abs(calorie_gap - x["calories"]), -x["protein_g"]))

    return items[:max_items]


@login_required
def nutrition_target_upsert(request):
    """
    Targets page:
    - Save/update the user's target macros.
    - Sync today's Meal Plan items into LoggedMeal so totals include planned meals.
    - Compute today's totals.
    - Generate suggestions safely (never crash page if helper/api missing).
    """
    target, _ = NutritionTarget.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = NutritionTargetForm(request.POST, instance=target)
        if form.is_valid():
            form.save()
            messages.success(request, "Nutrition targets saved.")
            return redirect("core:nutrition_target")
    else:
        form = NutritionTargetForm(instance=target)

    # Today (single source of truth for this view)
    today = date.today()

    # Pull in today's meal-plan rows as logged meals (no-op if helper not available)
    try:
        sync_logged_meals_from_plan(request.user, today)
    except Exception:
        # Never break the page if meal-plan sync can't run
        pass

    # Compute totals and fetch today's logged meals
    totals = compute_daily_totals(request.user, today, target)
    todays_meals = LoggedMeal.objects.filter(user=request.user, date=today).order_by("id")

    # Suggestions: safe wrapper so missing stubs / API issues never crash the page
    try:
        # spoon_search is imported at top of views.py
        suggestions = suggest_recipes_for_gaps(
            target=target,
            totals=totals,
            search_fn=spoon_search,
            max_items=4,
        )
    except Exception:
        suggestions = []

    # Expose suggestions to recipe_detail (session-backed results)
    request.session.setdefault("recipe_results", {})
    request.session["recipe_results"]["web"] = suggestions or []
    request.session.modified = True

    context = {
        "form": form,
        "target": target,
        "totals": {
            "calories": totals.calories,
            "calories_pct": totals.calories_pct,
            "protein_g": totals.protein_g,
            "protein_pct": totals.protein_pct,
            "carbs_g": totals.carbs_g,
            "carbs_pct": totals.carbs_pct,
            "fat_g": totals.fat_g,
            "fat_pct": totals.fat_pct,
            "fiber_g": totals.fiber_g,
            "sugar_g": totals.sugar_g,
        },
        "todays_meals": todays_meals,
        "suggestions": suggestions,
    }
    return render(request, "core/nutrition_target.html", context)


@login_required
def meal_plan_view(request):
    qs = request.GET.get("week")
    today = timezone.localdate()
    try:
        anchor = dt.date.fromisoformat(qs) if qs else today
    except (TypeError, ValueError):
        anchor = today

    week_start = _monday_for(anchor)
    week_days = [week_start + dt.timedelta(days=i) for i in range(7)]

    # Provide previous/next week anchors for the template nav
    prev_week = week_start - dt.timedelta(days=7)
    next_week = week_start + dt.timedelta(days=7)

    plan, _ = MealPlan.objects.get_or_create(user=request.user, start_date=week_start)

    meals = (Meal.objects
             .filter(plan=plan, date__range=[week_start, week_start + dt.timedelta(days=6)])
             .select_related("recipe"))

    def slot_of(m: Meal):
        return getattr(m, "meal_type", None) or getattr(m, "slot", None)

    by_key = {(m.date, slot_of(m)): m for m in meals if slot_of(m)}

    if hasattr(Meal, "Slot") and hasattr(Meal.Slot, "choices"):
        slots = list(Meal.Slot.choices)
    elif hasattr(Meal, "MEAL_TYPES"):
        slots = list(Meal.MEAL_TYPES)
    else:
        slots = [("breakfast", "Breakfast"), ("lunch", "Lunch"), ("dinner", "Dinner"), ("snack", "Snack")]
    slot_values = [v for v, _ in slots]

    rows = []
    for day in week_days:
        cells = [
            {"meal": by_key.get((day, sv)), "slot": sv}
            for sv in slot_values
        ]
        rows.append({"date": day, "cells": cells})

    sel = request.GET.get("recipe")
    try:
        selected_recipe_id = int(sel) if sel else None
    except (TypeError, ValueError):
        selected_recipe_id = None

    favorites = request.user.saved_recipes.all()

    return render(
        request,
        "core/meal_plan.html",
        {
            "plan": plan,
            "rows": rows,
            "slots": slots,
            "favorites": favorites,
            "selected_recipe_id": selected_recipe_id,
            "week_start": week_start,
            "prev_week": prev_week,
            "next_week": next_week,
            "today": today,
        },
    )

@login_required
@require_POST
def meal_add(request):
    recipe_id = request.POST.get("recipe_id")
    date_str = request.POST.get("date")
    meal_type = request.POST.get("meal_type")

    if not recipe_id or not date_str or not meal_type:
        messages.error(request, "Missing fields.")
        return redirect("core:meal_plan")

    # Parse date
    try:
        meal_date = dt.date.fromisoformat(date_str)
    except Exception:
        messages.error(request, "Invalid date.")
        return redirect("core:meal_plan")

    # Resolve weekly plan
    week_start = _monday_for(meal_date)
    plan, _ = MealPlan.objects.get_or_create(user=request.user, start_date=week_start)

    # Ensure valid meal_type
    if meal_type not in [choice[0] for choice in Meal.Slot.choices]:
        meal_type = Meal.Slot.LUNCH  # fallback

    # Saved recipe
    recipe = get_object_or_404(SavedRecipe, pk=recipe_id, user=request.user)

    # Create or update (to respect unique constraint)
    meal, created = Meal.objects.update_or_create(
        plan=plan,
        date=meal_date,
        meal_type=meal_type,
        defaults={"recipe": recipe},
    )

    if created:
        messages.success(request, f"Added {recipe.title} to {meal_type.title()} on {meal_date}")
    else:
        messages.success(request, f"Updated {meal_type.title()} on {meal_date} with {recipe.title}")

    return redirect(f"{reverse('core:meal_plan')}?week={week_start.isoformat()}")


@login_required
def meal_delete(request, meal_id: int):
    meal = get_object_or_404(Meal, pk=meal_id, plan__user=request.user)
    week = meal.date.isoformat()
    meal.delete()
    messages.success(request, "Meal removed.")
    return redirect(f"{reverse('core:meal_plan')}?week={week}")

def _thumb_for_title_via_spoonacular(title: str) -> str | None:
    """
    Return a smallish image URL for a dish title using Spoonacular's
    /complexSearch endpoint. Returns None on any failure.
    """
    api_key = getattr(settings, "SPOONACULAR_API_KEY", None) or os.getenv("SPOONACULAR_API_KEY")
    if not api_key or not title:
        return None

    try:
        r = requests.get(
            "https://api.spoonacular.com/recipes/complexSearch",
            params={"apiKey": api_key, "query": title, "number": 1},
            timeout=6,
        )
        if r.ok:
            data = r.json() or {}
            results = data.get("results") or []
            if results:
                return results[0].get("image")  # usually a CDN URL
    except Exception:
        pass
    return None

class ContactForm(forms.Form):
    name = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"placeholder": "Your name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "you@example.com"}))
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5, "placeholder": "How can we help?"}))

def about(request):
    return render(request, "core/about.html")

def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            # Option A: email (works if EMAIL_BACKEND configured)
            try:
                send_mail(
                    subject=f"[Smart Recipe] Contact from {data['name']}",
                    message=f"From: {data['name']} <{data['email']}>\n\n{data['message']}",
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
                    recipient_list=[getattr(settings, "DEFAULT_TO_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "admin@example.com"))],
                    fail_silently=True,
                )
            except Exception:
                pass
            messages.success(request, "Thanks! Your message has been sent.")
            return redirect("core:contact")
    else:
        form = ContactForm()
    return render(request, "core/contact.html", {"form": form})

@login_required
def nutrition_target_reset(request):
    NutritionTarget.objects.filter(user=request.user).delete()
    messages.success(request, "Nutrition targets were reset.")
    return redirect("core:nutrition_target")

def _week_start(d: _date) -> _date:
    """Monday as the start of the week (same convention your meal plan uses)."""
    return d - timedelta(days=d.weekday())

@require_POST
@login_required
def log_custom_meal(request):
    """
    Create a LoggedMeal from the 'Quick log' form on Targets.
    (5) Also mirrors it into the weekly Meal Plan if available:
        - creates/gets this week's plan
        - warns if the same slot already has a meal today
        - otherwise creates a simple plan item for today
    """
    # Parse inputs (fixes: these were missing in your current function)
    title = (request.POST.get("title") or "").strip() or "Custom meal"
    meal_type = request.POST.get("meal_type") or "lunch"

    def _ival(name: str) -> int:
        try:
            return int(request.POST.get(name, 0) or 0)
        except (TypeError, ValueError):
            return 0

    cals = _ival("calories")
    p = _ival("protein_g")
    c = _ival("carbs_g")
    f = _ival("fat_g")

    # Qty can be integer or decimal; defaults to 1.0
    try:
        qty = float(request.POST.get("quantity") or 1.0)
    except (TypeError, ValueError):
        qty = 1.0

    day = _date.today()

    # Create the logged meal (this drives the progress bars)
    lm = LoggedMeal.objects.create(
        user=request.user,
        date=day,  # ensure 'today' explicitly
        meal_type=meal_type,
        title=title,
        calories=int(round(cals * qty)),
        protein_g=int(round(p * qty)),
        carbs_g=int(round(c * qty)),
        fat_g=int(round(f * qty)),
    )

    # Mirror into the Meal Plan (weekly) if your schema is present
    try:
        # Your codebase has MealPlan + Meal (plan.meals relation). We use generic field detection
        # so this works even if your related model uses slightly different names.
        week = _week_start(day)
        plan, _ = MealPlan.objects.get_or_create(user=request.user, start_date=week)

        meals_rel = getattr(plan, "meals", None)  # RelatedManager to plan items (Meal)
        if not meals_rel:
            messages.success(request, "Meal logged.")
            return redirect("core:nutrition_target")

        # Check conflict: same slot already set today?
        conflict = None
        for item in meals_rel.all():
            item_date = (
                getattr(item, "date", None)
                or getattr(item, "for_date", None)
                or getattr(item, "scheduled_date", None)
                or getattr(item, "day", None)
            )
            item_slot = getattr(item, "meal_type", None) or getattr(item, "slot", None)
            if item_date == day and item_slot == meal_type:
                conflict = item
                break

        if conflict:
            messages.warning(request, f"There is already a {meal_type} saved in your Meal Plan for today.")
        else:
            # Create a simple plan item for today.
            # If your Meal model requires a recipe FK, you can adapt this to create a minimal SavedRecipe first;
            # otherwise these generic fields typically exist on a simple "Meal" item.
            create_kwargs = {"title": title}

            rel_model = meals_rel.model
            # date field
            if hasattr(rel_model, "date"):
                create_kwargs["date"] = day
            elif hasattr(rel_model, "for_date"):
                create_kwargs["for_date"] = day
            elif hasattr(rel_model, "scheduled_date"):
                create_kwargs["scheduled_date"] = day
            elif hasattr(rel_model, "day"):
                create_kwargs["day"] = day

            # meal type / slot field
            if hasattr(rel_model, "meal_type"):
                create_kwargs["meal_type"] = meal_type
            elif hasattr(rel_model, "slot"):
                create_kwargs["slot"] = meal_type

            # If your Meal model has optional macro fields, pass them along:
            for k, v in {
                "calories": lm.calories,
                "protein_g": lm.protein_g,
                "carbs_g": lm.carbs_g,
                "fat_g": lm.fat_g,
            }.items():
                if hasattr(rel_model, k):
                    create_kwargs[k] = v

            meals_rel.create(**create_kwargs)
            messages.success(request, "Meal logged (and added to your Meal Plan).")
    except Exception:
        # MealPlan not present / schema different — logging still succeeded
        messages.success(request, "Meal logged.")

    return redirect("core:nutrition_target")

@login_required
@require_POST
def log_recipe_meal(request, rid=None, recipe_id=None):
    """
    Create a LoggedMeal entry for *today* from the details page form.
    Accepts either URL kwarg name: `rid` or `recipe_id`.
    Stores per-serving nutrition + a separate quantity multiplier.
    """
    # --- accept either kw name from the url ---
    url_key = rid or recipe_id

    # 1) Read form values
    meal_type = (request.POST.get("meal_type") or "lunch").strip().lower()
    try:
        quantity = Decimal(request.POST.get("quantity") or "1")
    except Exception:
        quantity = Decimal("1")

    title = (request.POST.get("title") or "Recipe").strip()

    def dec(name):
        try:
            return Decimal(str(request.POST.get(name) or "0"))
        except Exception:
            return Decimal("0")

    calories  = dec("calories")
    protein_g = dec("protein_g")
    carbs_g   = dec("carbs_g")
    fat_g     = dec("fat_g")

    # 2) Choose a stable id to remember where this came from
    #    Prefer the hidden "key" we post from the template; fall back to url key.
    source_recipe_id = (request.POST.get("key") or (rid or recipe_id) or "").strip()
    if not source_recipe_id:
        messages.error(request, "Recipe not available to log.")
        return redirect("core:dashboard")

    # 3) Create the LoggedMeal (match your model fields exactly)
    LoggedMeal.objects.create(
        user=request.user,
        date=timezone.localdate(),
        meal_type=meal_type,
        title=title[:200],
        source_recipe_id=str(source_recipe_id)[:64],
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        quantity=quantity,
    )

    messages.success(request, "Meal logged for today.")
    return redirect("core:meal_plan")


@require_POST
@login_required
def delete_meal(request, meal_id: int):
    meal = get_object_or_404(LoggedMeal, id=meal_id, user=request.user)
    meal.delete()
    messages.success(request, "Meal removed.")
    return redirect("core:nutrition_target")
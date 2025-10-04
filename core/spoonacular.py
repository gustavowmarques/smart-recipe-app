import os
import re
import requests

SPOON_KEY = os.getenv("SPOONACULAR_API_KEY")


def _number_from_str(val) -> float:
    """Extract first number from strings like '270kcal', '12 g' -> 270.0 / 12.0"""
    s = str(val or "")
    m = re.search(r"[-+]?\d*\.?\d+", s)
    try:
        return float(m.group(0)) if m else 0.0
    except Exception:
        return 0.0


def _pick_macro(nutrients, name_prefix: str):
    """
    From Spoonacular 'nutrition.nutrients', pick first item whose name starts with prefix.
    Examples: 'Calories', 'Protein', 'Carbohydrates', 'Fat'
    """
    prefix = (name_prefix or "").lower()
    for n in nutrients or []:
        if (n.get("name") or "").lower().startswith(prefix):
            return n.get("amount")
    return None


def spoonacular_macros_for(
    external_id: str | int | None = None, title: str | None = None
) -> dict:
    """
    Return simple per-serving macros for a recipe:
    { calories, protein_g, carbs_g, fat_g }
    Strategy (best-effort):
      1) If we have a Spoonacular ID → try nutritionWidget.json (cheap),
         then fall back to information?includeNutrition=true.
      2) Else if we have a title → guessNutrition.
      3) On any error/limit → {} (caller can still save the favorite).
    """
    if not SPOON_KEY:
        return {}

    # 1) ID path: try widget first (lightweight)
    if external_id and str(external_id).isdigit():
        rid = str(external_id).strip()
        try:
            resp = requests.get(
                f"https://api.spoonacular.com/recipes/{rid}/nutritionWidget.json",
                params={"apiKey": SPOON_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json() or {}
                return {
                    "calories": _number_from_str(data.get("calories")),
                    "protein_g": _number_from_str(data.get("protein")),
                    "carbs_g": _number_from_str(data.get("carbs")),
                    "fat_g": _number_from_str(data.get("fat")),
                }
        except Exception:
            pass  # fall through to full information

        # Fallback: full information (heavier, but reliable)
        try:
            resp = requests.get(
                f"https://api.spoonacular.com/recipes/{rid}/information",
                params={"apiKey": SPOON_KEY, "includeNutrition": "true"},
                timeout=12,
            )
            if resp.status_code == 200:
                data = resp.json() or {}
                nutrients = (data.get("nutrition") or {}).get("nutrients") or []
                return {
                    "calories": _pick_macro(nutrients, "calories"),
                    "protein_g": _pick_macro(nutrients, "protein"),
                    "carbs_g": _pick_macro(nutrients, "carbo"),
                    "fat_g": _pick_macro(nutrients, "fat"),
                }
        except Exception:
            pass

    # 2) Title path: guessNutrition
    if title:
        try:
            resp = requests.get(
                "https://api.spoonacular.com/recipes/guessNutrition",
                params={"title": title, "apiKey": SPOON_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                g = resp.json() or {}
                return {
                    "calories": (g.get("calories") or {}).get("value"),
                    "protein_g": (g.get("protein") or {}).get("value"),
                    "carbs_g": (g.get("carbs") or {}).get("value"),
                    "fat_g": (g.get("fat") or {}).get("value"),
                }
        except Exception:
            pass

    # 3) Give up gracefully
    return {}


def spoonacular_recipe_info(sid: str) -> dict:
    """
    Fetch full Spoonacular details for a recipe id and normalize
    the fields that recipe_detail() expects.
    """
    sid = (sid or "").strip()
    if not sid or not SPOON_KEY:
        return {}

    try:
        resp = requests.get(
            f"https://api.spoonacular.com/recipes/{sid}/information",
            params={"apiKey": SPOON_KEY, "includeNutrition": "true"},
            timeout=12,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json() or {}
        return {
            "id": data.get("id"),
            "title": data.get("title"),
            "image": data.get("image"),
            "extendedIngredients": data.get("extendedIngredients") or [],
            "analyzedInstructions": data.get("analyzedInstructions") or [],
            "instructions": data.get("instructions") or "",
            "readyInMinutes": data.get("readyInMinutes"),
            "servings": data.get("servings"),
            "sourceUrl": data.get("sourceUrl"),
            "nutrition": data.get("nutrition") or {},
        }
    except Exception:
        return {}

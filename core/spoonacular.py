# core/spoonacular.py (or in views.py if you prefer)
import os, requests

SPOON_KEY = os.getenv("SPOONACULAR_API_KEY", "")

def _pick_macro(nutrients, name):
    for n in nutrients or []:
        if (n.get("name") or "").lower().startswith(name):
            # ensure grams for Protein/Carbs/Fat; Calories in kcal
            return n.get("amount")
    return None

def spoonacular_macros_for(external_id=None, title=None):
    """
    Returns dict: {"calories": Decimal|float|None, "protein_g": ..., "carbs_g": ..., "fat_g": ...}
    Uses best available Spoonacular endpoint.
    """
    if not SPOON_KEY:
        return {}

    try:
        if external_id and str(external_id).isdigit():
            # ID flow
            url = f"https://api.spoonacular.com/recipes/{external_id}/information"
            resp = requests.get(url, params={"includeNutrition": "true", "apiKey": SPOON_KEY}, timeout=6)
            resp.raise_for_status()
            data = resp.json()
            nutrients = (data.get("nutrition") or {}).get("nutrients") or []
            return {
                "calories": _pick_macro(nutrients, "calories"),
                "protein_g": _pick_macro(nutrients, "protein"),
                "carbs_g": _pick_macro(nutrients, "carbo"),
                "fat_g": _pick_macro(nutrients, "fat"),
            }
        # Title guess (AI or unknown id)
        if title:
            url = "https://api.spoonacular.com/recipes/guessNutrition"
            resp = requests.get(url, params={"title": title, "apiKey": SPOON_KEY}, timeout=6)
            resp.raise_for_status()
            g = resp.json() or {}
            # guessNutrition gives calories.value, carbs.value, protein.value, fat.value
            return {
                "calories": (g.get("calories") or {}).get("value"),
                "protein_g": (g.get("protein") or {}).get("value"),
                "carbs_g": (g.get("carbs") or {}).get("value"),
                "fat_g": (g.get("fat") or {}).get("value"),
            }
    except Exception:
        # swallow errors: prefill is best-effort
        pass
    return {}

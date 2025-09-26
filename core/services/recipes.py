"""
Service wrapper for Spoonacular API search.
Provides spoon_search(query, ...) → list of dicts with real recipe data.

Each dict will look like:
{
    "id": 715421,
    "title": "Chicken Alfredo",
    "image": "https://spoonacular.com/recipeImages/715421-312x231.jpg",
    "calories": 520,
    "protein_g": 40,
}
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)

# Spoonacular base URL and API key (from environment)
SPOON_BASE = "https://api.spoonacular.com/recipes/complexSearch"
API_KEY = os.getenv("SPOONACULAR_API_KEY")


def spoon_search(query, number: int = 10, min_protein: int | None = None, max_calories: int | None = None):
    """
    Search Spoonacular recipes and return normalized dicts.
    :param query: search string
    :param number: how many results to request
    :param min_protein: optional min protein filter (g)
    :param max_calories: optional max calories filter (kcal)
    :return: list of dicts
    """
    if not API_KEY:
        logger.warning("Spoonacular API key not set; returning empty results.")
        return []

    params = {
        "apiKey": API_KEY,
        "query": query,
        "number": number,
        "addRecipeNutrition": True,  # ensures nutrients are included
    }
    if min_protein:
        params["minProtein"] = min_protein
    if max_calories:
        params["maxCalories"] = max_calories

    try:
        resp = requests.get(SPOON_BASE, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("Spoonacular API error: %s", e, exc_info=True)
        return []

    results = []
    for r in data.get("results", []):
        rid = r.get("id")
        if not rid:
            continue

        title = r.get("title", "Recipe")
        image = r.get("image")  # full URL (Spoonacular always provides this if available)

        # Extract nutrition
        protein_g = 0
        calories = 0
        nutrients = (r.get("nutrition") or {}).get("nutrients", [])
        if isinstance(nutrients, list):
            for n in nutrients:
                name = (n.get("name") or "").lower()
                if name == "protein":
                    try:
                        protein_g = int(round(float(n.get("amount") or 0)))
                    except Exception:
                        pass
                elif name == "calories":
                    try:
                        calories = int(round(float(n.get("amount") or 0)))
                    except Exception:
                        pass

        results.append(
            {
                "id": rid,
                "title": title,
                "image": image,
                "calories": calories,
                "protein_g": protein_g,
            }
        )

    return results

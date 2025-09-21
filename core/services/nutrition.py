from __future__ import annotations
from dataclasses import dataclass
from datetime import date as _date, timedelta

# Try to import models used by totals/sync. If missing, keep functions no-op.
try:
    from core.models import LoggedMeal
except Exception:
    LoggedMeal = None  # type: ignore

try:
    # Your MealPlan model (weekly) with fields: id, meals, start_date, user, user_id
    # Each plan has related "meals" items; we don't know their field names, so we read them defensively.
    from core.models import MealPlan
except Exception:
    MealPlan = None  # type: ignore

@dataclass
class DailyTotals:
    calories: int = 0
    protein_g: int = 0
    carbs_g:   int = 0
    fat_g:     int = 0
    fiber_g:   int = 0
    sugar_g:   int = 0

    calories_pct: int = 0
    protein_pct:  int = 0
    carbs_pct:    int = 0
    fat_pct:      int = 0

def _pct(n: int, d: int) -> int:
    if not d or d <= 0:
        return 0
    return max(0, min(200, round((n / d) * 100)))  # clamp 0..200% for UI

def compute_daily_totals(user, day: date, target) -> DailyTotals:
    """
    Sums today's intake. If LoggedMeal model is absent, returns zeros — the UI still works.
    """
    totals = DailyTotals()

    if LoggedMeal is not None:
        qs = LoggedMeal.objects.filter(user=user, date=day)
        for m in qs:
            totals.calories += getattr(m, "calories", 0) or 0
            totals.protein_g += getattr(m, "protein_g", 0) or 0
            totals.carbs_g   += getattr(m, "carbs_g", 0) or 0
            totals.fat_g     += getattr(m, "fat_g", 0) or 0
            totals.fiber_g   += getattr(m, "fiber_g", 0) or 0
            totals.sugar_g   += getattr(m, "sugar_g", 0) or 0

    # percentages vs target
    totals.calories_pct = _pct(totals.calories, getattr(target, "calories", 0) or 0)
    totals.protein_pct  = _pct(totals.protein_g, getattr(target, "protein_g", 0) or 0)
    totals.carbs_pct    = _pct(totals.carbs_g,   getattr(target, "carbs_g", 0) or 0)
    totals.fat_pct      = _pct(totals.fat_g,     getattr(target, "fat_g", 0) or 0)
    return totals


def suggest_recipes_for_gaps(target, totals, search_fn, max_items=4):
    """
    search_fn: callable like search_fn(query, min_protein=None, max_calories=None) -> list[dict]
    Returns a short list of recipes that help close today's gaps.
    """
    suggestions = []
    need_protein = max(0, (target.protein_g or 0) - (totals.protein_g or 0))
    need_cal     = max(0, (target.calories  or 0) - (totals.calories  or 0))

    # Simple heuristic:
    if need_protein >= 25:
        suggestions += search_fn("high protein quick", min_protein=25, max_calories=None)[:max_items]
    elif need_cal >= 300:
        suggestions += search_fn("balanced dinner", min_protein=15, max_calories=600)[:max_items]
    else:
        suggestions += search_fn("light snack", min_protein=10, max_calories=300)[:max_items]

    return suggestions[:max_items]

def _week_start(day: _date) -> _date:
    # Monday as start of week (adjust if your app uses Sunday)
    return day - timedelta(days=day.weekday())

def sync_logged_meals_from_plan(user, day: _date):
    """
    Copy today's MealPlan items into LoggedMeal so totals can sum them.
    Works with a weekly MealPlan (fields: start_date, meals related manager).
    Safely no-ops if models/fields differ.
    """
    if LoggedMeal is None or MealPlan is None:
        return

    # Find this week's plan(s) for the user
    start = _week_start(day)
    # Some projects allow multiple weeks open; include the exact start_date match first,
    # and (defensively) include any plan where start_date is within last 6 days.
    plans = MealPlan.objects.filter(user=user, start_date__gte=start, start_date__lte=start)

    # If your ORM/DB stores start_date with timezones, widen the window:
    if not plans.exists():
        plans = MealPlan.objects.filter(user=user, start_date__gte=start - timedelta(days=6),
                                        start_date__lte=start)

    for plan in plans:
        meals_rel = getattr(plan, "meals", None)
        if not meals_rel:
            continue

        for item in meals_rel.all():
            # Try common field names for the scheduled date
            item_date = (
                getattr(item, "date", None)
                or getattr(item, "for_date", None)
                or getattr(item, "scheduled_date", None)
                or getattr(item, "day", None)
            )
            if item_date != day:
                continue

            meal_type = getattr(item, "meal_type", None) or getattr(item, "slot", None) or "lunch"
            recipe_id = (
                getattr(item, "recipe_id", None)
                or getattr(item, "recipeId", None)
                or getattr(item, "recipe_id_str", None)
                or ""
            )
            recipe_id = str(recipe_id or "")

            # Skip if we already logged this recipe for this slot/day
            exists = LoggedMeal.objects.filter(
                user=user, date=day, meal_type=meal_type, source_recipe_id=recipe_id
            ).exists()
            if exists:
                continue

            title = (
                getattr(item, "title", None)
                or getattr(item, "recipe_title", None)
                or "Planned meal"
            )

            cals = getattr(item, "calories", 0) or 0
            prot = getattr(item, "protein_g", 0) or 0
            carbs = getattr(item, "carbs_g", 0) or 0
            fat  = getattr(item, "fat_g", 0) or 0

            LoggedMeal.objects.create(
                user=user,
                date=day,
                meal_type=meal_type,
                title=title,
                source_recipe_id=recipe_id,
                calories=int(cals),
                protein_g=int(prot),
                carbs_g=int(carbs),
                fat_g=int(fat),
            )
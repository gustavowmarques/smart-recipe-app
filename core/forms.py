from django import forms
from .models import Ingredient, SavedRecipe, NutritionTarget, PantryImageUpload, Meal


class IngredientForm(forms.ModelForm):
    class Meta:
        model = Ingredient
        fields = ["name", "quantity", "unit"]
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "e.g. bell pepper",
                "class": "form-control"
            }),
            "quantity": forms.TextInput(attrs={
                "placeholder": "e.g. 2 or 200",
                "class": "form-control"
            }),
            "unit": forms.TextInput(attrs={
                "placeholder": "e.g. g, pcs",
                "class": "form-control"
            }),
        }

    def clean_name(self):
        # light normalization; keep original capitalization in DB if you prefer
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Please enter an ingredient name.")
        return name


class SavedRecipeForm(forms.ModelForm):
    """
    Form for creating/editing SavedRecipe (your DB-backed favorite/manual recipe).

    NOTE: `ingredients_json` and `steps_json` are JSON fields.
    For now, keep input as valid JSON arrays (e.g. ["2 eggs", "200g flour"]).
    """
    ingredients_json = forms.JSONField(
        required=False,
        help_text='Enter a JSON array, e.g. ["2 eggs", "200g flour"]',
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": '["2 eggs", "200g flour"]'
        }),
    )
    steps_json = forms.JSONField(
        required=False,
        help_text='Enter a JSON array, e.g. ["Beat eggs", "Cook for 5 min"]',
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": '["Beat eggs", "Cook for 5 min"]'
        }),
    )

    class Meta:
        model = SavedRecipe
        fields = ["title", "image_url", "ingredients_json", "steps_json", "source", "external_id"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Recipe title"}),
            "image_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://..."}),
            "source": forms.Select(attrs={"class": "form-select"}),
            "external_id": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "(optional) keep blank for manual recipes"
            }),
        }

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise forms.ValidationError("Please enter a title.")
        return title

class NutritionTargetForm(forms.ModelForm):
    class Meta:
        model = NutritionTarget
        fields = [
            "calories",
            "protein_g", "carbs_g", "fat_g",
            "fiber_g", "sugar_g",
            "diet_type",
        ]
        widgets = {
            "calories": forms.NumberInput(attrs={"min": 0, "class": "form-control", "placeholder": "2000"}),
            "protein_g": forms.NumberInput(attrs={"min": 0, "class": "form-control", "placeholder": "140"}),
            "carbs_g": forms.NumberInput(attrs={"min": 0, "class": "form-control", "placeholder": "200"}),
            "fat_g": forms.NumberInput(attrs={"min": 0, "class": "form-control", "placeholder": "70"}),
            "fiber_g": forms.NumberInput(attrs={"min": 0, "class": "form-control"}),
            "sugar_g": forms.NumberInput(attrs={"min": 0, "class": "form-control"}),
            "diet_type": forms.Select(attrs={"class": "form-select"}),
        }

class PantryImageUploadForm(forms.ModelForm):
    class Meta:
        model = PantryImageUpload
        fields = ["image"]  # keep it minimal for now
        widgets = {
            "image": forms.ClearableFileInput(attrs={"class": "form-control"})
        }

# A tiny helper for adding meals to a plan
def _slot_choices():
    """
    Return choices for the meal slot/type, regardless of how the model defined it.
    Tries Meal.Slot.choices first, then Meal.MEAL_TYPES, then a safe fallback.
    """
    # Django TextChoices pattern: class Slot(models.TextChoices): ...
    if hasattr(Meal, "Slot") and hasattr(Meal.Slot, "choices"):
        return list(Meal.Slot.choices)

    # Older/manual style tuple on the model
    if hasattr(Meal, "MEAL_TYPES"):
        return list(Meal.MEAL_TYPES)

    # Last-resort fallback so server still runs
    return [
        ("breakfast", "Breakfast"),
        ("lunch", "Lunch"),
        ("dinner", "Dinner"),
        ("snack", "Snack"),
    ]

# ---- meal add form ---------------------------------------------------------

class MealAddForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    slot = forms.ChoiceField(choices=[])  # filled in __init__

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(Meal, "Slot") and hasattr(Meal.Slot, "choices"):
            self.fields["slot"].choices = list(Meal.Slot.choices)
        elif hasattr(Meal, "MEAL_TYPES"):
            self.fields["slot"].choices = list(Meal.MEAL_TYPES)
        else:
            self.fields["slot"].choices = [
                ("breakfast", "Breakfast"),
                ("lunch", "Lunch"),
                ("dinner", "Dinner"),
                ("snack", "Snack"),
            ]

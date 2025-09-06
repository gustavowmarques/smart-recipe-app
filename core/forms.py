from django import forms
from .models import Ingredient, SavedRecipe


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

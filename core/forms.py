from django import forms
from .models import Ingredient

class IngredientForm(forms.ModelForm):
    class Meta:
        model = Ingredient
        fields = ["name", "quantity", "unit"]
        widgets = {
            "name": forms.TextInput(attrs={"class":"form-control", "placeholder":"e.g., chicken breast"}),
            "quantity": forms.TextInput(attrs={"class":"form-control", "placeholder":"e.g., 2"}),
            "unit": forms.TextInput(attrs={"class":"form-control", "placeholder":"e.g., pcs, g"}),
        }

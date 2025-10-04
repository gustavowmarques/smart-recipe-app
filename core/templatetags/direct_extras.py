from django import template

register = template.Library()


@register.filter(name="get_item")
def get_item(mapping, key):
    """
    Safe dict-like lookup usable in templates.

    Usage: {{ mydict|get_item:some_key }}
    - Returns None when the key is missing or the object isn't a mapping.
    - Works for nested lookups when combined, e.g.:
        {% with inner=outer|get_item:day %}
        {% with meal=inner|get_item:'breakfast' %}
            {{ meal }}
        {% endwith %}
        {% endwith %}
    """
    try:
        if hasattr(mapping, "get"):
            return mapping.get(key)
        # Fallback for objects supporting __getitem__
        return mapping[key]
    except Exception:
        return None


@register.filter
def split(s, sep):
    return s.split(sep)

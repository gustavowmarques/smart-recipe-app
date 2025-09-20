from django import template
register = template.Library()

@register.filter
def chunk(seq, size: int):
    try:
        size = int(size)
    except Exception:
        size = 3
    seq = list(seq or [])
    return [seq[i:i+size] for i in range(0, len(seq), size)]

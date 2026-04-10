from django import template

register = template.Library()


@register.filter
def add_class(field, css_class: str):
    """Render a bound field's widget with an extra CSS class."""
    if field is None:
        return ""

    attrs = {}
    existing = field.field.widget.attrs.get("class", "")
    existing = existing.strip()
    css_class = (css_class or "").strip()

    if existing and css_class:
        attrs["class"] = f"{existing} {css_class}"
    elif css_class:
        attrs["class"] = css_class
    elif existing:
        attrs["class"] = existing

    return field.as_widget(attrs=attrs)

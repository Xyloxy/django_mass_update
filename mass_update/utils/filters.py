from django.template.defaulttags import register


@register.filter(name="mass_update_get_first_field")
def get_first_field(item_list: list) -> str:
    return str(item_list[0])


@register.filter(name="mass_update_stringify")
def stringify(obj: list) -> str:
    return ",".join(str(s) for s in obj)

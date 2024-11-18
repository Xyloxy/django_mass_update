from django.conf import settings

_default_settings = {
    "ADD_GLOBALLY": True,
}

mass_update_settings = getattr(settings, "mass_update", _default_settings)

ADD_GLOBALLY = mass_update_settings.get("ADD_GLOBALLY", _default_settings["ADD_GLOBALLY"])
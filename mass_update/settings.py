from django.conf import settings

_default_settings = {
    "ADD_GLOBALLY": True,
    "BATCH_SIZE": 500,
}

mass_update_settings = getattr(settings, "mass_update", _default_settings)

def get_default(name):
    return mass_update_settings.get(name, _default_settings[name])


ADD_GLOBALLY = get_default("ADD_GLOBALLY")
BATCH_SIZE = get_default("BATCH_SIZE")
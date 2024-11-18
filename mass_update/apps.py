from django.apps import AppConfig
from django.contrib import admin
from . import settings
from .mass_update import mass_update_action


class MassUpdateConfig(AppConfig):
    name = "mass_update"
    verbose_name = "Mass update"

    def ready(self):
        if settings.ADD_GLOBALLY:
            admin.site.add_action(mass_update_action)

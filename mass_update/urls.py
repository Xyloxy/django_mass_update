from django.urls import path
from .mass_update import mass_update_change_view

urlpatterns = [
    path(
        "<str:app_name>/<str:model_name>-mass-update/<str:object_ids>/",
        mass_update_change_view,
        name="mass_update_change_view",
    ),
]

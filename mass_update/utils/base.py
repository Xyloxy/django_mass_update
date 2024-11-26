from django.apps import apps
from django.contrib.admin import ModelAdmin
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.contrib.admin.sites import AdminSite
from django.http.request import HttpRequest
from django.db.models import Model

from mass_update.utils.updaters import FormSetMassUpdate, FastMassUpdate

from typing import Any, List, Generator


class MassUpdateBase(ModelAdmin):
    """
    This base is created to keep obvious / basic functionality separate of core code,
    so it is easier to read the code.
    """

    def __init__(
        self,
        app_name: str,
        model_name: str,
        admin_site: AdminSite,
        request: HttpRequest,
        object_ids: list,
    ) -> None:
        self.app_name: str = app_name
        self.model_name: str = model_name
        self.model: Model = apps.get_model(app_name, model_name)
        self.request: HttpRequest = request
        self.object_ids: list = object_ids
        self.fields_to_update: list = []

        """Class used to process data, taken from mass_update.utils.updaters module."""
        self.processing_model = FormSetMassUpdate()

        try:
            self.admin_obj: ModelAdmin = admin_site._registry[self.model]
        except KeyError:
            raise Exception("Model not registered with the admin site.")

        """First object from object_ids"""
        self.obj = self.base_qs.get(pk=self.object_ids[0])

        if not self.admin_obj.has_change_permission(self.request, self.obj):
            raise PermissionDenied

        super(MassUpdateBase, self).__init__(self.model, admin_site)

    @property
    def model_fields(self) -> List[Any]:
        """All non-hidden fields of the model."""
        return self.model._meta.get_fields(include_hidden=False)

    @property
    def model_fields_names(self) -> Generator[str, Any, Any]:
        """All editable and non-unique fields of the model."""
        for field in self.model_fields:
            if getattr(field, "unique", True) and not getattr(field, "editable", False):
                continue

            yield field.name

    @property
    def admin_url(self):
        """Admin changelist URL."""
        return reverse(
            "%s:%s_%s_changelist"
            % (
                self.admin_site.name,
                self.model._meta.app_label,
                self.model._meta.model_name,
            )
        )

    @property
    def base_qs(self):
        """
        Base queryset for admin and request. `massupdate_queryset` is an overridable function,
        in case user wants to create their own custom queryset.
        """
        return getattr(
            self.admin_obj, "massupdate_queryset", self.admin_obj.get_queryset
        )(self.request)

    def set_processing(self, form_sets_on):
        """Set processing model for mass update."""
        if form_sets_on == "on":
            self.processing_model = FormSetMassUpdate()
        else:
            self.processing_model = FastMassUpdate()

    def get_base_context(self):
        """Generates base context for proper rendering of the template."""
        from django.contrib.contenttypes.models import ContentType

        return {
            "add": False,
            "change": True,
            "has_add_permission": self.has_add_permission(self.request),
            "has_change_permission": self.has_change_permission(self.request, self.obj),
            "has_view_permission": self.has_view_permission(self.request, self.obj),
            "has_delete_permission": self.has_delete_permission(self.request, self.obj),
            "has_file_field": True,
            "has_absolute_url": hasattr(self.model, "get_absolute_url"),
            "form_url": "",
            "opts": self.model._meta,
            "content_type_id": ContentType.objects.get_for_model(self.model).id,
            "save_as": self.save_as,
            "save_on_top": self.save_on_top,
            "field_names": self.model_fields_names,
            "fields_to_update": self.fields_to_update,
        }

    def get_template_paths(self, template_name: str) -> List[str]:
        """Generates template paths for rendering of the template."""
        return [
            "admin/%s/%s/%s.html"
            % (self.app_name, self.model._meta.object_name.lower(), template_name),
            "admin/%s/%s.html" % (self.model._meta.app_label, template_name),
            "admin/%s.html" % template_name,
        ]

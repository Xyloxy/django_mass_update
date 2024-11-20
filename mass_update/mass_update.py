from django.contrib.admin import ModelAdmin, site as default_admin_site
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.views.decorators import staff_member_required

from django.utils.translation import gettext_lazy as _
from . import settings
import hashlib
from django.http import HttpResponseRedirect
from django.urls import reverse
from typing import Any, List, Generator
from django.db.models import QuerySet
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.apps import apps
from django.shortcuts import render
from django.core.exceptions import PermissionDenied
from django.template.defaulttags import register
from django.contrib.auth.decorators import permission_required


@register.filter(name="mass_update_get_item")
def get_item(dictionary, key):
    return dictionary.get(key, "")


def get_mass_update_url(model: Any, pks: List[int], session: Any) -> str:
    """Generates a url for mass update

    Args:
        model (Any): User selected model metadata
        pks (list): Primary keys of selected objects
        session (Any): User session

    Returns:
        str: Mass update url
    """
    object_ids = ",".join(str(s) for s in pks)
    hash_id = "session-%s" % hashlib.md5(object_ids.encode("utf-8")).hexdigest()
    session[hash_id] = object_ids
    session.save()

    return reverse(
        "mass_update_change_view",
        kwargs={
            "app_name": model.app_label,
            "model_name": model.model_name,
            "session_id": hash_id,
        },
    )


def mass_update_action(
    modeladmin: Any, request: HttpRequest, queryset: QuerySet
) -> HttpResponse:
    """Action function for mass update.

    Args:
        modeladmin (Any): Model Admin
        request (HttpRequest): User Request
        queryset (QuerySet): User's Django Admin interface QuerySet

    Returns:
        HttpResponse: Redirect to mass update page
    """
    selected = queryset.values_list("pk", flat=True)

    redirect_url = get_mass_update_url(
        modeladmin.model._meta, selected, request.session
    )

    redirect_url = add_preserved_filters(
        {
            "preserved_filters": modeladmin.get_preserved_filters(request),
            "opts": queryset.model._meta,
        },
        redirect_url,
    )

    return HttpResponseRedirect(redirect_url)


mass_update_action.short_description = _("Mass Update")


# @permission_required("mass_update.mass_update", raise_exception=True)
@staff_member_required
def mass_update_change_view(
    request: HttpRequest,
    app_name: str,
    model_name: str,
    session_id,
    admin_site=None,
):
    object_ids: str = request.session.get(session_id)
    object_ids: List[int] = [int(x) for x in object_ids.split(",")]

    mass_update = MassUpdate(
        app_name,
        model_name,
        admin_site or default_admin_site,
        request,
        object_ids,
    )

    if request.method == "POST":
        mass_update.set_fields_to_update(request.POST.getlist("to_update"))
        return mass_update.get_view()
    else:
        return mass_update.get_field_update_view()


mass_update_change_view = staff_member_required(mass_update_change_view)


class MassUpdate(ModelAdmin):
    def __init__(self, app_name, model_name, admin_site, request, object_ids):
        self.app_name = app_name
        self.model_name = model_name
        self.model = apps.get_model(app_name, model_name)
        self.request = request
        self.object_ids = object_ids
        self.fields_to_update = []

        try:
            self.admin_obj = admin_site._registry[self.model]
        except KeyError:
            raise Exception("Model not registered with the admin site.")

        # if not self.has_change_permission(self.request, self.model):
        #     raise PermissionDenied

        super(MassUpdate, self).__init__(self.model, admin_site)

    @property
    def model_fields(self) -> List[Any]:
        return self.model._meta.get_fields(include_hidden=False)

    @property
    def model_fields_names(self) -> Generator[str, Any, Any]:
        for field in self.model_fields:
            yield field.name

    @property
    def unique_model_fields(self) -> List[Any]:
        unique_model_fields = []

        for field in self.model_fields:
            try:
                if field.unique and field.editable:
                    unique_model_fields.append(field)
            except Exception:
                pass

        return unique_model_fields

    @property
    def unique_model_fields_names(self) -> Generator[str, Any, Any]:
        for field in self.unique_model_fields:
            yield field.name

    def set_fields_to_update(self, fields):
        self.fields_to_update = fields

    def get_base_context(self):
        from django.contrib.contenttypes.models import ContentType

        queryset = getattr(self.admin_obj, "massadmin_queryset", self.get_queryset)(
            self.request
        )
        obj = queryset.get(pk=self.object_ids[0])

        return {
            "add": False,
            "change": True,
            "has_add_permission": self.has_add_permission(self.request),
            "has_change_permission": self.has_change_permission(self.request, obj),
            "has_view_permission": self.has_view_permission(self.request, obj),
            "has_delete_permission": self.has_delete_permission(self.request, obj),
            "has_file_field": True,
            "has_absolute_url": hasattr(self.model, "get_absolute_url"),
            "form_url": "",
            "opts": self.model._meta,
            "content_type_id": ContentType.objects.get_for_model(self.model).id,
            "save_as": self.save_as,
            "save_on_top": self.save_on_top,
            "unique_field_names": self.unique_model_fields_names,
            "field_names": self.model_fields_names,
            "fields_to_update": self.fields_to_update,
        }

    def get_template_paths(self, template_name: str) -> List[str]:
        return [
            "admin/%s/%s/%s.html"
            % (self.app_name, self.model._meta.object_name.lower(), template_name),
            "admin/%s/%s.html" % (self.model._meta.app_label, template_name),
            "admin/%s.html" % template_name,
        ]

    def get_field_update_view(self):
        return render(
            self.request,
            self.get_template_paths("mass_update_fields_to_update_form"),
            self.get_base_context(),
        )

    def get_view(self):
        context = self.get_base_context()

        qs = self.model.objects.filter(pk=self.object_ids[0])

        context.update({"field_values": qs.values(*self.fields_to_update)[0]})

        return render(
            self.request,
            self.get_template_paths("mass_update_form"),
            context,
        )


class MassUpdateMixin:
    actions = (mass_update_action,)

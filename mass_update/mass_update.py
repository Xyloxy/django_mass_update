from django.apps import apps
from django.contrib.admin import ModelAdmin, site as default_admin_site, helpers
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import QuerySet

from django.http import HttpResponseRedirect
from django.http.request import HttpRequest
from django.http.response import HttpResponse

from django.shortcuts import render
from django.template.defaulttags import register
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

import hashlib
from typing import Any, List, Generator

from .helpers import FormSetMassUpdate, FastMassUpdate, VALID

from django.core.exceptions import ValidationError


@register.filter(name="mass_update_get_item")
def get_item(dictionary, key):
    return dictionary.get(key, "")


@register.filter(name="mass_update_stringify")
def stringify(obj):
    return ",".join(str(s) for s in obj)


def set_session(session, object):
    hash_id = hashlib.md5(object.encode("utf-8")).hexdigest()
    hash_id = "session-%s" % hash_id
    session[hash_id] = object
    session.save()
    return hash_id


def get_mass_update_url(model: Any, pks: List[int], session: Any) -> str:
    """Generates a url for mass update

    Args:
        model (Any): User selected model metadata
        pks (list): Primary keys of selected objects
        session (Any): User session

    Returns:
        str: Mass update url
    """
    object_ids = stringify(pks)
    hash_id = set_session(session, object_ids)

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
        if not request.POST.get("mass_update"):
            mass_update.fields_to_update = request.POST.getlist("to_update")
            return mass_update.get_view()
        else:
            mass_update.set_processing(form_sets_on=request.POST.get("form_sets_on"))

            fields_to_update = [
                str(x) for x in request.POST.get("mass_update").split(",")
            ]

            field_dict = {}
            for field in fields_to_update:
                field_dict[field] = request.POST.get(field)

            mass_update.fields_to_update = fields_to_update

            return mass_update.process_change(field_dict)
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

        self.processing_model = FormSetMassUpdate()

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

    @property
    def admin_url(self):
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
        return getattr(self.admin_obj, "massadmin_queryset", self.get_queryset)(
            self.request
        )

    def set_processing(self, form_sets_on):
        if form_sets_on == "on":
            self.processing_model = FormSetMassUpdate()
        else:
            self.processing_model = FastMassUpdate()

    def get_base_context(self):
        from django.contrib.contenttypes.models import ContentType

        obj = self.base_qs.get(pk=self.object_ids[0])

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

    def get_view(self, error=None):
        context = self.get_base_context()

        qs = self.base_qs.filter(pk=self.object_ids[0])
        first_object_values = qs.values(*self.fields_to_update)[0]

        model_form = self.get_form(
            self.request, self.base_qs.get(pk=self.object_ids[0])
        )()

        for field in self.fields_to_update:
            model_form.initial[field] = first_object_values[field]

        fieldsets = self.admin_obj.get_fieldsets(self.request, qs)
        for fieldset in fieldsets:
            fieldset[1]["fields"] = [field for field in fieldset[1]["fields"] if field in self.fields_to_update]

        admin_form = helpers.AdminForm(
            form=model_form,
            fieldsets=fieldsets,
            prepopulated_fields=self.admin_obj.get_prepopulated_fields(
                self.request, qs
            ),
            readonly_fields=self.admin_obj.get_readonly_fields(self.request, qs),
            model_admin=self.admin_obj,
        )

        context.update(
            {
                "field_values": first_object_values,
                "admin_form": admin_form,
                "error": error,
            }
        )

        return render(
            self.request,
            self.get_template_paths("mass_update_form"),
            context,
        )

    def process_change(self, field_dict):
        result = self.processing_model.edit_all_values(
            request=self.request,
            queryset=self.base_qs,
            object_ids=self.object_ids,
            fields_to_update=self.fields_to_update,
            data=field_dict,
            model_admin=self,
        )

        if result == VALID:
            msg = "Mass update successful. Edited %s objects" % len(self.object_ids)
            self.message_user(self.request, msg)
            redirect_url = add_preserved_filters(
                {
                    "preserved_filters": self.get_preserved_filters(self.request),
                    "opts": self.model._meta,
                },
                self.admin_url,
            )
            return HttpResponseRedirect(redirect_url)
        else:
            raise self.get_view(self, result[2])


class MassUpdateMixin:
    actions = (mass_update_action,)

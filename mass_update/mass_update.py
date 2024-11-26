from django.contrib.admin import site as default_admin_site, helpers
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import QuerySet

from django.http import HttpResponseRedirect
from django.http.request import HttpRequest
from django.http.response import HttpResponse

from django.shortcuts import render
from django.urls import reverse
from django.utils.safestring import mark_safe
# TODO(Xyloxy): Add translations
# from django.utils.translation import gettext_lazy as _

import hashlib
from typing import Any, List

from mass_update.utils.updaters import VALID
from mass_update.utils.base import MassUpdateBase


def set_session(session, object: List[int]) -> str:
    """Set session for mass update

    Args:
        session (Any): User session
        object (List[int]): Selected objects

    Returns:
        str: Hashed session id
    """
    hash_id = hashlib.md5(object.encode("utf-8")).hexdigest()
    session[hash_id] = object
    session.save()
    return hash_id


def get_mass_update_url(model: Any, pks: List[int], session: Any) -> str:
    """
    Generates a url for mass update, and creates a session.

    Args:
        model (Any): User selected model metadata
        pks (list): Primary keys of selected objects
        session (Any): User session

    Returns:
        str: Mass update url
    """
    object_ids = ",".join(str(s) for s in pks)
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
    selected: List[Any] = queryset.values_list("pk", flat=True)

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


mass_update_action.short_description = "Mass Update"


# TODO(Xyloxy): Add custom permissions
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
            if not mass_update.fields_to_update:
                return mass_update.get_field_update_view()
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


class MassUpdate(MassUpdateBase):
    def get_field_update_view(self) -> HttpResponse:
        return render(
            self.request,
            self.get_template_paths("mass_update_fields_to_update_form"),
            self.get_base_context(),
        )

    def get_view(self, error: str = None, errors: List[Any] = None) -> HttpResponse:
        context = self.get_base_context()

        qs = self.base_qs.filter(pk=self.object_ids[0])

        model_form = self.admin_obj.get_form(self.request, self.obj)(instance=self.obj)
        model_form._errors = errors

        admin_form = helpers.AdminForm(
            form=model_form,
            fieldsets=self.admin_obj.get_fieldsets(self.request, qs),
            prepopulated_fields=self.admin_obj.get_prepopulated_fields(
                self.request, qs
            ),
            readonly_fields=self.admin_obj.get_readonly_fields(self.request, qs),
            model_admin=self.admin_obj,
        )
        media = self.media + admin_form.media

        context.update(self.admin_site.each_context(self.request))

        context.update(
            {
                "admin_form": admin_form,
                "error": error,
                "media": mark_safe(media),
            }
        )

        return render(
            self.request,
            self.get_template_paths("mass_update_form"),
            context,
        )

    def process_change(self, field_dict: dict):
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
            return self.get_view(result[2], result[1])


class MassUpdateMixin:
    actions = (mass_update_action,)

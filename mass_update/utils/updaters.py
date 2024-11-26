from django.contrib.admin import helpers, ModelAdmin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.formsets import all_valid
from django.forms.models import ModelForm
from django.http.request import HttpRequest
from django.db.models import QuerySet

import sys
from mass_update import settings

VALID = "valid"


class FormSetMassUpdate:
    """
    Class using built-in django FormSets to save data.
    It's less efficient than FastMassUpdate, but gives better error logs, and can't
    cause unforseen issues.
    """

    def edit_all_values(
        self,
        request,
        queryset,
        object_ids,
        fields_to_update,
        model_admin,
        **kwargs,
    ):
        """
        Edits all values for the given object IDs.

        Args:
            request (HttpRequest): The current request.
            queryset (QuerySet): The queryset of objects to edit.
            object_ids (list): The IDs of the objects to edit.
            fields_to_update (list): The fields to update.
            model_admin (ModelAdmin): Instance of the calling object.

        Returns:
            tuple: A tuple containing the formsets, errors, errors list, and general error.
        """
        formsets = []
        errors, errors_list = None, None

        try:
            with transaction.atomic():
                objects = queryset.filter(pk__in=object_ids)
                for obj in objects:
                    model_form = model_admin.get_form(
                        request, queryset.get(pk=object_ids[0])
                    )
                    form = model_form(request.POST, request.FILES, instance=obj)
                    form.fields = {
                        k: v for k, v in form.fields.items() if k in fields_to_update
                    }

                    if form.is_valid():
                        model_admin.save_form(request, form, change=True)
                        new_object = form.instance
                    else:
                        new_object = obj

                    for FormSet, _ in model_admin.get_formsets_with_inlines(
                        request, new_object
                    ):
                        prefix = FormSet.get_default_prefix()
                        if prefix in fields_to_update:
                            formset = FormSet(
                                request.POST,
                                request.FILES,
                                instance=new_object,
                                prefix=prefix,
                            )
                            formsets.append(formset)

                    if all_valid(formsets) and form.is_valid():
                        model_admin.save_model(request, new_object, form, change=True)
                        form.save_m2m()
                        for formset in formsets:
                            model_admin.save_formset(
                                request, form, formset, change=True
                            )

                        change_message = model_admin.construct_change_message(
                            request, form, formsets
                        )
                        model_admin.log_change(request, new_object, change_message)
                    else:
                        errors = form.errors
                        errors_list = helpers.AdminErrorList(form, formsets)
                        raise ValidationError("Not all forms is correct")

                return VALID

        except Exception as e:
            general_error = e
            return (formsets, errors, errors_list, general_error)


class FastMassUpdate:
    """
    Class using built-in django .update and .set model functions to save data.
    It's more efficient than FormSetMassUpdate, but gives worse error logs, and could
    cause unforseen issues.
    """

    def validate_form(
        self,
        request: HttpRequest,
        model_form: ModelForm,
        fields_to_update: list,
        obj: object,
        data: dict,
    ) -> dict:
        """
        Validates a single object to test for any user error

        Only one form needs to be validated, as the same fields are being used
        for all objects, and form only checks edited fields, other cases are being
        checked during update

        Args:
            request (HttpRequest): The current request.
            model_form (ModelAdmin): Instance of model_form of the obj.
            fields_to_update (list): The fields to update.
            obj (object): The object to validate.
            data (dict): Data.

        Returns:
            dict: Cleaned data.
        """
        form = model_form(request.POST, request.FILES, instance=obj)
        for fieldname, field in list(form.fields.items()):
            if fieldname not in fields_to_update:
                del form.fields[fieldname]

        # Django might automatically invalidate the field before sending
        # so we have to catch it in an efficient way, as creating a new
        # form for each object (which there will be a lot),
        # is very process intensive
        is_valid = True
        for field in fields_to_update:
            if "invalid" in str(data[field]):
                is_valid = False

        if not form.is_valid() or not is_valid:
            raise ValidationError(form.errors)

        return form.cleaned_data

    def get_data(self, model_admin: ModelAdmin, data: dict) -> tuple[dict, dict]:
        """
        Splits data between m2m and normal fields

        Args:
            model_admin (ModelAdmin): Instance of the calling object.
            data (dict): Data.

        Returns:
            tuple: A tuple containing the data and m2m_data as dicts.
        """
        m2m_data = {}
        data = {}

        for name, value in data.items():
            if (
                model_admin.model._meta.get_field(name).get_internal_type()
                == "ManyToManyField"
            ):
                m2m_data[name] = value
            else:
                data[name] = value

        return (data, m2m_data)

    def edit_all_values(
        self,
        request: HttpRequest,
        queryset: QuerySet,
        object_ids: list[int],
        fields_to_update: list,
        model_admin: ModelAdmin,
        data: dict,
        **kwargs,
    ):
        """
        Edits all values for the given object IDs.

        Args:
            request (HttpRequest): The current request.
            queryset (QuerySet): The queryset of objects to edit.
            object_ids (list): The IDs of the objects to edit.
            fields_to_update (list): The fields to update.
            model_admin (ModelAdmin): Instance of the calling object.
            data (dict): Data.

        Returns:
            tuple: A tuple containing the formsets, errors, errors list, and general error.
        """
        object_id = object_ids[0]

        try:
            obj = queryset.get(pk=object_id)
            model_form = model_admin.get_form(request, obj)

            data = self.validate_form(request, model_form, fields_to_update, obj, data)
            data, m2m_data = self.get_data(model_admin, data)

            m2m_fields = []
            for field in fields_to_update:
                if hasattr(obj, field) and hasattr(getattr(obj, field), "set"):
                    m2m_fields.append(field)

            with transaction.atomic():
                i = 0
                while i < len(object_ids):
                    transaction_objects = queryset.filter(
                        pk__in=object_ids[i : i + settings.BATCH_SIZE]
                    )

                    transaction_objects.update(**data)

                    # Handle M2M fields, slow!
                    if m2m_fields:
                        for j in range(0, len(transaction_objects)):
                            for field in m2m_fields:
                                obj = transaction_objects[j]
                                m2m_field = getattr(obj, field)
                                m2m_field.set(m2m_data[field])
                                obj.save()

                    i += settings.BATCH_SIZE

            return VALID

        except Exception:
            general_error = sys.exc_info()[1]

        return ([], None, general_error, None)

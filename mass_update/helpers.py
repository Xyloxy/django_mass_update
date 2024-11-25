from django.contrib.admin import helpers
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.formsets import all_valid

import sys
from . import settings

VALID = "valid"


class FormSetMassUpdate:
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
            model_form (ModelForm): The form to use for editing.
            mass_changes_fields (list): The fields to update.

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
    def validate_form(self, request, model_form, fields_to_update, obj, data):
        """
        Validates a single object to test for any user error

        Only one form needs to be validated, as the same fields are being used
        for all objects, and form only checks edited fields, other cases are being
        checked during update
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

    def edit_all_values(
        self,
        request,
        queryset,
        object_ids,
        fields_to_update,
        model_admin,
        data,
        **kwargs,
    ):
        object_id = object_ids[0]

        try:
            obj = queryset.get(pk=object_id)

            model_form = model_admin.get_form(request, queryset.get(pk=object_ids[0]))

            data = self.validate_form(request, model_form, fields_to_update, obj, data)
            m2m_data = {}

            # Get M2M fields and remove them from data
            temp_data = {}
            for field_name, value in data.items():
                if (
                    model_admin.model._meta.get_field(field_name).get_internal_type()
                    == "ManyToManyField"
                ):
                    m2m_data[field_name] = value
                else:
                    temp_data[field_name] = value

            data = temp_data

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
                    m2m_field = getattr(obj, field)
                    m2m_field.set(m2m_data[field])

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

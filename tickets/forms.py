from django import forms
from django.contrib.auth import get_user_model

from .models import Ticket, TicketTemplate


class TicketTemplateForm(forms.ModelForm):
    class Meta:
        model = TicketTemplate
        fields = [
            "title",
            "description",
            "active",
            "frequency",
            "interval",
            "start_date",
            "weekly_weekday",
            "monthly_day",
            "assignment_mode",
            "fixed_assignee",
            "points",
            "counts_for_score",
            "tags",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "frequency": forms.Select(attrs={"class": "form-select"}),
            "interval": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "weekly_weekday": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 6}),
            "monthly_day": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 28}),
            "assignment_mode": forms.Select(attrs={"class": "form-select"}),
            "fixed_assignee": forms.Select(attrs={"class": "form-select"}),
            "points": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "counts_for_score": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "tags": forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fixed_assignee"].queryset = get_user_model().objects.filter(is_active=True).order_by("username", "id")


class TicketUpdateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["title", "description", "assignee", "status", "priority", "counts_for_score", "tags"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "assignee": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "counts_for_score": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "tags": forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
        }


class TicketCreateForm(TicketUpdateForm):
    template = forms.ModelChoiceField(
        label="Template",
        queryset=TicketTemplate.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = TicketTemplate.objects.filter(active=True).order_by("title")

    class Meta(TicketUpdateForm.Meta):
        fields = ["template"] + TicketUpdateForm.Meta.fields

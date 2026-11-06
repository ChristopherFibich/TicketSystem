from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import CalendarSubscription, Ticket, TicketTemplate


class CalendarAppointmentForm(forms.Form):
    title = forms.CharField(
        label="Title",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Descriptive title"}),
    )
    notes = forms.CharField(
        label="Notes",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Additional notes"}),
    )
    starts_at = forms.DateTimeField(
        label="Start",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"class": "form-control", "type": "datetime-local"}),
    )
    ends_at = forms.DateTimeField(
        label="End",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"class": "form-control", "type": "datetime-local"}),
    )
    attendees = forms.ModelMultipleChoiceField(
        label="Attending users",
        queryset=get_user_model().objects.none(),
        required=True,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 5}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attendees"].queryset = get_user_model().objects.filter(is_active=True).order_by("username", "id")

    def clean(self):
        cleaned_data = super().clean()
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")
        if starts_at and timezone.is_naive(starts_at):
            starts_at = timezone.make_aware(starts_at, timezone.get_current_timezone())
            cleaned_data["starts_at"] = starts_at
        if ends_at and timezone.is_naive(ends_at):
            ends_at = timezone.make_aware(ends_at, timezone.get_current_timezone())
            cleaned_data["ends_at"] = ends_at
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "The end must be after the start.")
        return cleaned_data


class CalendarSubscriptionForm(forms.ModelForm):
    url = forms.CharField(
        label="iCal URL",
        widget=forms.URLInput(attrs={"class": "form-control", "placeholder": "https://...", "type": "url"}),
    )

    class Meta:
        model = CalendarSubscription
        fields = ["name", "url"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "z. B. Arbeit"}),
        }

    def clean_url(self):
        url = self.cleaned_data["url"].strip()
        if url.lower().startswith("webcal://"):
            url = "https://" + url[9:]
        if not url.lower().startswith(("http://", "https://")):
            raise forms.ValidationError("Only http, https, and webcal links are supported.")
        return url


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
        self.fields["eligible_users"] = forms.ModelMultipleChoiceField(
            label="Eligible users",
            queryset=get_user_model().objects.filter(is_active=True).order_by("username", "id"),
            required=False,
            widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
            help_text="For pool assignment, select the users who may receive this template. Leave empty to include everyone active.",
        )


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

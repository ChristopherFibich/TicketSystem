from django import forms

from .models import Ticket, TicketTemplate


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

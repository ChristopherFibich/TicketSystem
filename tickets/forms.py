from django import forms

from .models import Ticket, TicketTemplate


class TicketForm(forms.ModelForm):

    template = forms.ModelChoiceField(
        label="Template",
        queryset=TicketTemplate.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = TicketTemplate.objects.filter(active=True).order_by("title")

    class Meta:
        model = Ticket
        fields = ["template", "title", "description", "assignee", "status", "counts_for_score", "tags"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "assignee": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "counts_for_score": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "tags": forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
        }

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.urls import path

from .models import Completion, Tag, Ticket, TicketTemplate, TicketTemplateEligibility
from .scheduling import next_scheduled_for


class TicketTemplateEligibilityInline(admin.TabularInline):
	model = TicketTemplateEligibility
	extra = 1
	autocomplete_fields = ["user"]


@admin.register(TicketTemplate)
class TicketTemplateAdmin(admin.ModelAdmin):
	list_display = [
		"title",
		"active",
		"frequency",
		"interval",
		"assignment_mode",
		"fixed_assignee",
		"counts_for_score",
		"next_scheduled_for_display",
	]
	list_filter = ["active", "frequency", "assignment_mode", "counts_for_score"]
	search_fields = ["title", "description"]
	autocomplete_fields = ["fixed_assignee"]
	inlines = [TicketTemplateEligibilityInline]
	filter_horizontal = ["tags"]
	actions = ["add_tags_action"]

	class AddTagsForm(forms.Form):
		tags = forms.ModelMultipleChoiceField(
			label="Tags to add",
			queryset=Tag.objects.all(),
			required=True,
			widget=admin.widgets.FilteredSelectMultiple("tags", is_stacked=False),
		)

	@admin.action(description="Add tags to selected templates")
	def add_tags_action(self, request: HttpRequest, queryset):
		if "apply" in request.POST:
			form = self.AddTagsForm(request.POST)
			if form.is_valid():
				tags = list(form.cleaned_data["tags"])
				updated = 0
				for template in queryset:
					template.tags.add(*tags)
					updated += 1
				self.message_user(
					request,
					f"Added {len(tags)} tag(s) to {updated} template(s).",
					level=messages.SUCCESS,
				)
				return redirect("admin:tickets_tickettemplate_changelist")
		else:
			form = self.AddTagsForm()

		context = dict(
			self.admin_site.each_context(request),
			title="Add tags to templates",
			templates=queryset,
			form=form,
			action_name="add_tags_action",
		)
		return render(request, "admin/tickets/tickettemplate/add_tags.html", context)

	def save_related(self, request, form, formsets, change):
		# Let the admin save inlines (eligibilities) first.
		super().save_related(request, form, formsets, change)

		template: TicketTemplate = form.instance
		if template.assignment_mode != "POOL":
			return

		# If the user didn't specify an eligible pool, default to "everyone".
		if template.eligibilities.exists():
			return

		User = get_user_model()
		users = User.objects.filter(is_active=True).only("id")
		TicketTemplateEligibility.objects.bulk_create(
			[TicketTemplateEligibility(template=template, user=u, weight=1) for u in users],
			ignore_conflicts=True,
		)

	@admin.display(description="Next scheduled for")
	def next_scheduled_for_display(self, obj: TicketTemplate):
		try:
			return next_scheduled_for(obj)
		except Exception:
			return "—"


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
	list_display = ["title", "status", "assignee", "template", "scheduled_for_date", "created_at", "completed_at"]
	list_filter = ["status", "template"]
	search_fields = ["title", "description"]
	autocomplete_fields = ["assignee", "created_by", "template"]
	filter_horizontal = ["tags"]
	change_list_template = "admin/tickets/ticket/change_list.html"
	actions = ["add_tags_action"]

	class AddTagsForm(forms.Form):
		tags = forms.ModelMultipleChoiceField(
			label="Tags to add",
			queryset=Tag.objects.all(),
			required=True,
			widget=admin.widgets.FilteredSelectMultiple("tags", is_stacked=False),
		)

	@admin.action(description="Add tags to selected tickets")
	def add_tags_action(self, request: HttpRequest, queryset):
		if "apply" in request.POST:
			form = self.AddTagsForm(request.POST)
			if form.is_valid():
				tags = list(form.cleaned_data["tags"])
				updated = 0
				for ticket in queryset:
					ticket.tags.add(*tags)
					updated += 1
				self.message_user(request, f"Added {len(tags)} tag(s) to {updated} ticket(s).", level=messages.SUCCESS)
				return redirect("admin:tickets_ticket_changelist")
		else:
			form = self.AddTagsForm()

		context = dict(
			self.admin_site.each_context(request),
			title="Add tags to tickets",
			tickets=queryset,
			form=form,
			action_name="add_tags_action",
		)
		return render(request, "admin/tickets/ticket/add_tags.html", context)

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path(
				"reset-data/",
				self.admin_site.admin_view(self.reset_data_view),
				name="tickets_ticket_reset_data",
			),
		]
		return custom_urls + urls

	def reset_data_view(self, request: HttpRequest):
		if not request.user.is_superuser:
			self.message_user(request, "Superuser privileges required.", level=messages.ERROR)
			return redirect("admin:tickets_ticket_changelist")

		mode = request.GET.get("mode") or "scores"
		allowed_modes = {
			"scores": "Reset scores only (delete completions)",
			"tickets": "Reset tickets + scores (delete tickets and completions)",
		}
		if mode not in allowed_modes:
			mode = "scores"

		if request.method == "POST":
			confirm = (request.POST.get("confirm") or "").strip()
			mode = request.POST.get("mode") or mode
			if mode not in allowed_modes:
				mode = "scores"

			if confirm != "RESET":
				self.message_user(request, "Confirmation failed. Type RESET to proceed.", level=messages.ERROR)
				return redirect(f"admin:tickets_ticket_reset_data")

			if mode == "scores":
				Completion.objects.all().delete()
				self.message_user(request, "Scores reset: all completions deleted.", level=messages.SUCCESS)
			elif mode == "tickets":
				Completion.objects.all().delete()
				Ticket.objects.all().delete()
				self.message_user(request, "Tickets reset: all tickets and completions deleted.", level=messages.SUCCESS)

			return redirect("admin:tickets_ticket_changelist")

		context = dict(
			self.admin_site.each_context(request),
			title="Reset TicketSystem data",
			mode=mode,
			modes=allowed_modes,
		)
		return render(request, "admin/tickets/ticket/reset_data.html", context)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
	list_display = ["name", "created_at"]
	search_fields = ["name"]


@admin.register(Completion)
class CompletionAdmin(admin.ModelAdmin):
	list_display = ["ticket", "completed_by", "points_awarded", "completed_at", "time_to_complete_seconds"]
	list_filter = ["completed_by"]
	autocomplete_fields = ["ticket", "completed_by"]

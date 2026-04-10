from django.contrib import admin

from .models import Completion, Ticket, TicketTemplate, TicketTemplateEligibility
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


@admin.register(Completion)
class CompletionAdmin(admin.ModelAdmin):
	list_display = ["ticket", "completed_by", "points_awarded", "completed_at", "time_to_complete_seconds"]
	list_filter = ["completed_by"]
	autocomplete_fields = ["ticket", "completed_by"]

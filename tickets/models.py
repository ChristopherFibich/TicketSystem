from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class TicketStatus(models.TextChoices):
	NEW = "NEW", "New"
	DOING = "DOING", "Doing"
	DONE = "DONE", "Done"


class RecurrenceFrequency(models.TextChoices):
	DAILY = "DAILY", "Daily"
	WEEKLY = "WEEKLY", "Weekly"
	MONTHLY = "MONTHLY", "Monthly"


class AssignmentMode(models.TextChoices):
	FIXED = "FIXED", "Fixed"
	POOL = "POOL", "Eligible pool (fair random)"


class TicketTemplate(models.Model):
	title = models.CharField(max_length=200)
	description = models.TextField(blank=True)
	active = models.BooleanField(default=True)

	frequency = models.CharField(max_length=10, choices=RecurrenceFrequency.choices)
	interval = models.PositiveSmallIntegerField(default=1)
	start_date = models.DateField(default=timezone.localdate)

	weekly_weekday = models.PositiveSmallIntegerField(
		null=True,
		blank=True,
		help_text="0=Mon ... 6=Sun (weekly only).",
	)
	monthly_day = models.PositiveSmallIntegerField(
		null=True,
		blank=True,
		help_text="1-28 (monthly only).",
	)

	assignment_mode = models.CharField(
		max_length=10,
		choices=AssignmentMode.choices,
		default=AssignmentMode.POOL,
	)
	fixed_assignee = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="fixed_templates",
	)

	points = models.PositiveSmallIntegerField(default=1)
	counts_for_score = models.BooleanField(
		default=True,
		help_text="If unchecked, completing tickets from this template awards 0 points and doesn't affect scoring.",
	)

	tags = models.ManyToManyField("Tag", blank=True, related_name="templates")
	last_scheduled_for = models.DateField(null=True, blank=True)
	last_completed_for = models.DateField(
		null=True,
		blank=True,
		help_text="Date when a ticket from this template was last completed. Used to schedule the next occurrence.",
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["title"]

	def __str__(self) -> str:
		return self.title


class TicketTemplateEligibility(models.Model):
	template = models.ForeignKey(TicketTemplate, on_delete=models.CASCADE, related_name="eligibilities")
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="template_eligibilities")
	weight = models.PositiveSmallIntegerField(default=1)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["template", "user"], name="unique_template_user_eligibility"),
		]

	def __str__(self) -> str:
		return f"{self.template} -> {self.user} (w={self.weight})"


class Tag(models.Model):
	name = models.CharField(max_length=50, unique=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["name"]

	def __str__(self) -> str:
		return self.name


class Ticket(models.Model):
	template = models.ForeignKey(TicketTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets")
	scheduled_for_date = models.DateField(null=True, blank=True, db_index=True)

	title = models.CharField(max_length=200)
	description = models.TextField(blank=True)
	status = models.CharField(max_length=10, choices=TicketStatus.choices, default=TicketStatus.NEW)

	counts_for_score = models.BooleanField(
		default=True,
		help_text="If unchecked, completing this ticket awards 0 points and doesn't affect scoring.",
	)

	tags = models.ManyToManyField("Tag", blank=True, related_name="tickets")

	assignee = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="assigned_tickets",
	)
	assigned_at = models.DateTimeField(null=True, blank=True)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="created_tickets",
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	completed_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["status", "-created_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["template", "scheduled_for_date"],
				condition=Q(template__isnull=False) & Q(scheduled_for_date__isnull=False),
				name="unique_template_scheduled_date",
			),
		]

	def __str__(self) -> str:
		return self.title

	def save(self, *args, **kwargs):
		# Track assignment age independently from created_at.
		now = timezone.now()

		if self.pk:
			old = Ticket.objects.filter(pk=self.pk).values("assignee_id").first()
			old_assignee_id = old["assignee_id"] if old else None
			if old_assignee_id != self.assignee_id:
				self.assigned_at = now if self.assignee_id else None
		else:
			if self.assignee_id and self.assigned_at is None:
				self.assigned_at = now

		return super().save(*args, **kwargs)

	def mark_done(self, completed_by) -> "Completion":
		if self.status == TicketStatus.DONE:
			try:
				return self.completion
			except Completion.DoesNotExist:
				pass

		now = timezone.now()
		self.status = TicketStatus.DONE
		self.completed_at = now
		self.save(update_fields=["status", "completed_at", "updated_at"])

		points = 1
		if self.template_id and self.template:
			if self.template.counts_for_score:
				points = int(self.template.points or 1)
			else:
				points = 0
		else:
			points = 1 if self.counts_for_score else 0

		time_to_complete_seconds = None
		if self.created_at:
			delta: timedelta = now - self.created_at
			time_to_complete_seconds = max(0, int(delta.total_seconds()))

		completion, _ = Completion.objects.get_or_create(
			ticket=self,
			defaults={
				"completed_by": completed_by,
				"completed_at": now,
				"points_awarded": points,
				"time_to_complete_seconds": time_to_complete_seconds,
			},
		)

		if self.template_id and self.template:
			self.template.last_completed_for = timezone.localdate(now)
			self.template.save(update_fields=["last_completed_for", "updated_at"])
		return completion


class Completion(models.Model):
	ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="completion")
	completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="completions")
	completed_at = models.DateTimeField(default=timezone.now)
	points_awarded = models.PositiveSmallIntegerField(default=1)
	time_to_complete_seconds = models.PositiveIntegerField(null=True, blank=True)

	class Meta:
		ordering = ["-completed_at"]

	def __str__(self) -> str:
		return f"{self.ticket} by {self.completed_by}"

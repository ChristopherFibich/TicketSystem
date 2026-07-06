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


class TicketPriority(models.TextChoices):
	LOW = "LOW", "Low"
	MED = "MED", "Med"
	HIGH = "HIGH", "High"


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
	priority = models.CharField(max_length=10, choices=TicketPriority.choices, default=TicketPriority.MED)

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
				return self.completions.get(completed_by=completed_by)
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
			completed_by=completed_by,
			defaults={
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
	ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="completions")
	completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="completions")
	completed_at = models.DateTimeField(default=timezone.now)
	points_awarded = models.PositiveSmallIntegerField(default=1)
	time_to_complete_seconds = models.PositiveIntegerField(null=True, blank=True)

	class Meta:
		ordering = ["-completed_at"]
		constraints = [
			models.UniqueConstraint(fields=["ticket", "completed_by"], name="unique_ticket_completed_by"),
		]

	def __str__(self) -> str:
		return f"{self.ticket} by {self.completed_by}"


class PetType(models.TextChoices):
	CAT = "CAT", "Cat"
	DOG = "DOG", "Dog"


class FeedTime(models.TextChoices):
	MORNING = "AM", "Morning"
	EVENING = "PM", "Evening"


class PetFeedStatus(models.Model):
	day = models.DateField(db_index=True)
	pet = models.CharField(max_length=3, choices=PetType.choices)
	time = models.CharField(max_length=2, choices=FeedTime.choices)
	fed = models.BooleanField(default=False)

	updated_at = models.DateTimeField(auto_now=True)
	updated_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="pet_feed_updates",
	)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["day", "pet", "time"], name="unique_pet_feed_per_day"),
		]
		ordering = ["-day", "pet", "time"]

	def __str__(self) -> str:
		return f"{self.day} {self.pet} {self.time}: {'fed' if self.fed else 'not fed'}"


class DashboardPerson(models.TextChoices):
	CHRIS = "CHRIS", "Chris"
	MICHELLE = "MICHELLE", "Michelle"


class DashboardSupplement(models.TextChoices):
	MULTIVITAMIN = "MULTIVITAMIN", "Multivitamin"
	VITAMIN_B12 = "VITAMIN_B12", "Vitamin B12"
	CREATINE = "CREATINE", "Creatine"
	PILLE = "PILLE", "Pille"


class SupplementStatus(models.Model):
	day = models.DateField(db_index=True)
	person = models.CharField(max_length=10, choices=DashboardPerson.choices)
	supplement = models.CharField(max_length=20, choices=DashboardSupplement.choices)
	taken = models.BooleanField(default=False)

	updated_at = models.DateTimeField(auto_now=True)
	updated_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="supplement_updates",
	)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["day", "person", "supplement"], name="unique_supplement_per_day"),
		]
		ordering = ["-day", "person", "supplement"]

	def __str__(self) -> str:
		return f"{self.day} {self.person} {self.supplement}: {'taken' if self.taken else 'not taken'}"


class DashboardWidgetKind(models.TextChoices):
	PET_FEED = "PET_FEED", "Pet feed switches"
	TOGGLES = "TOGGLES", "Custom switches"
	SHOPPING_PREVIEW = "SHOPPING_PREVIEW", "Shopping list preview"
	TICKETS_STALE = "TICKETS_STALE", "Tickets: not done for N days"


class DashboardWidget(models.Model):
	kind = models.CharField(max_length=30, choices=DashboardWidgetKind.choices)
	title = models.CharField(max_length=100, blank=True)
	order = models.PositiveSmallIntegerField(default=10)
	enabled = models.BooleanField(default=True)

	# Toggle widget config
	toggles_show_30d_stats = models.BooleanField(default=False)

	# Widget config (used by some kinds)
	tickets_min_age_days = models.PositiveSmallIntegerField(default=7)
	tickets_limit = models.PositiveSmallIntegerField(default=10)

	class Meta:
		ordering = ["order", "id"]

	def __str__(self) -> str:
		name = self.get_kind_display() if hasattr(self, "get_kind_display") else self.kind
		return self.title or name


class DashboardToggleGroup(models.Model):
	title = models.CharField(max_length=100)
	order = models.PositiveSmallIntegerField(default=10)
	enabled = models.BooleanField(default=True)

	class Meta:
		ordering = ["order", "id"]

	def __str__(self) -> str:
		return self.title


class DashboardToggle(models.Model):
	group = models.ForeignKey(DashboardToggleGroup, on_delete=models.CASCADE, related_name="toggles")
	slug = models.SlugField(max_length=50)
	label = models.CharField(max_length=100)
	order = models.PositiveSmallIntegerField(default=10)
	enabled = models.BooleanField(default=True)

	class Meta:
		ordering = ["order", "id"]
		constraints = [
			models.UniqueConstraint(fields=["group", "slug"], name="unique_toggle_slug_per_group"),
		]

	def __str__(self) -> str:
		return f"{self.group}: {self.label}"


class DashboardToggleStatus(models.Model):
	day = models.DateField(db_index=True)
	toggle = models.ForeignKey(DashboardToggle, on_delete=models.CASCADE, related_name="statuses")
	on = models.BooleanField(default=False)

	updated_at = models.DateTimeField(auto_now=True)
	updated_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="dashboard_toggle_updates",
	)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["day", "toggle"], name="unique_dashboard_toggle_per_day"),
		]
		ordering = ["-day", "toggle_id"]

	def __str__(self) -> str:
		return f"{self.day} {self.toggle}: {'on' if self.on else 'off'}"


class WeightEntry(models.Model):
	measured_on = models.DateField(db_index=True)
	weight_kg = models.DecimalField(max_digits=5, decimal_places=1)
	created_at = models.DateTimeField(auto_now_add=True)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="weight_entries",
	)

	class Meta:
		ordering = ["measured_on", "created_at"]

	def __str__(self) -> str:
		return f"{self.created_by} {self.measured_on}: {self.weight_kg} kg"


class ShoppingItem(models.Model):
	text = models.CharField(max_length=200)
	checked = models.BooleanField(default=False)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="shopping_items_created",
	)

	class Meta:
		ordering = ["checked", "-created_at"]

	def __str__(self) -> str:
		return self.text

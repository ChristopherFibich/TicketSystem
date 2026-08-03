from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tickets.models import (
    AssignmentMode,
    Ticket,
    TicketStatus,
    TicketTemplate,
    UserAvailability,
)
from tickets.scheduling import next_scheduled_for

User = get_user_model()

@dataclass(frozen=True)
class Candidate:
    user: User
    weight: int


def choose_assignee(template: TicketTemplate) -> User | None:
    if template.assignment_mode == AssignmentMode.FIXED:
        return template.fixed_assignee

    absent_user_ids = set(UserAvailability.objects.filter(is_absent=True).values_list("user_id", flat=True))
    elig = list(template.eligibilities.select_related("user"))
    candidates = [Candidate(e.user, max(1, int(e.weight))) for e in elig if e.user.is_active and e.user_id not in absent_user_ids]
    if not elig:
        from django.contrib.auth import get_user_model

        UserModel = get_user_model()
        users = UserModel.objects.filter(is_active=True).exclude(id__in=absent_user_ids)
        candidates = [Candidate(u, 1) for u in users]
    if not candidates:
        return None

    weights = [c.weight for c in candidates]
    return random.choices([c.user for c in candidates], weights=weights, k=1)[0]


class Command(BaseCommand):
    help = "Spawn tickets from active recurring templates (intended for cron)."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="date", help="Run as if today is YYYY-MM-DD")
        parser.add_argument("--dry-run", action="store_true", help="Show what would happen without creating tickets")
        parser.add_argument("--max-per-template", type=int, default=90, help="Safety limit for catch-up spawning")
        parser.add_argument(
            "--recreate-daily",
            action="store_true",
            help="Delete existing tickets and reset anchors for templates tagged Daily before spawning once.",
        )

    def handle(self, *args, **options):
        if options.get("date"):
            today = date.fromisoformat(options["date"])
        else:
            today = timezone.localdate()

        dry_run: bool = bool(options["dry_run"])
        max_per_template: int = int(options["max_per_template"])
        recreate_daily: bool = bool(options["recreate_daily"])

        templates = TicketTemplate.objects.filter(active=True).order_by("id")
        if not templates.exists():
            self.stdout.write("No active templates.")
            return

        created_count = 0
        for template in templates:
            if recreate_daily and template.tags.filter(name__iexact="Daily").exists():
                if not dry_run:
                    Ticket.objects.filter(template=template).delete()
                    template.last_scheduled_for = None
                    template.last_completed_for = None
                    template.save(update_fields=["last_scheduled_for", "last_completed_for", "updated_at"])
                else:
                    self.stdout.write(f"[{template.id}] {template.title}: DRY-RUN reset Daily template")

            created_count += self._spawn_for_template(
                template,
                today=today,
                dry_run=dry_run,
                max_per_template=max_per_template,
            )

        self.stdout.write(self.style.SUCCESS(f"Done. Created {created_count} ticket(s)."))

    def _spawn_for_template(
        self,
        template: TicketTemplate,
        today: date,
        dry_run: bool,
        max_per_template: int,
    ) -> int:
        if template.interval < 1:
            raise CommandError(f"Template '{template}' has interval < 1")

        if template.frequency == "WEEKLY" and template.weekly_weekday is not None:
            if template.weekly_weekday > 6:
                raise CommandError(f"Template '{template}' has invalid weekly_weekday")
        if template.frequency == "MONTHLY" and template.monthly_day is not None:
            if not (1 <= template.monthly_day <= 28):
                raise CommandError(f"Template '{template}' has invalid monthly_day; use 1-28")

        # New recurrence semantics: schedule is based on completion.
        # Only spawn the *next* ticket once the previous one has been completed.
        if Ticket.objects.filter(template=template).exclude(status=TicketStatus.DONE).exists():
            self.stdout.write(f"[{template.id}] {template.title}: pending ticket exists; skipping")
            return 0

        next_date = next_scheduled_for(template)
        if next_date > today:
            self.stdout.write(f"[{template.id}] {template.title}: next due {next_date} (not yet)")
            return 0

        if Ticket.objects.filter(template=template, scheduled_for_date=next_date).exists():
            self.stdout.write(f"[{template.id}] {template.title}: already exists for {next_date}")
            return 0

        assignee = choose_assignee(template)
        if template.assignment_mode == AssignmentMode.FIXED and assignee is None:
            raise CommandError(f"Template '{template}' is FIXED but has no fixed_assignee")
        if template.assignment_mode == AssignmentMode.POOL and assignee is None:
            self.stdout.write(f"[{template.id}] {template.title}: no available pool users (all absent?); skipping")
            return 0

        msg = f"[{template.id}] {template.title}: create ticket for {next_date} -> {assignee}"
        if dry_run:
            self.stdout.write("DRY-RUN " + msg)
            return 0

        with transaction.atomic():
            ticket = Ticket.objects.create(
                template=template,
                scheduled_for_date=next_date,
                title=template.title,
                description=template.description,
                status=TicketStatus.NEW,
                assignee=assignee,
                counts_for_score=template.counts_for_score,
            )
            if template.tags.exists():
                ticket.tags.set(template.tags.all())
            template.last_scheduled_for = next_date
            template.save(update_fields=["last_scheduled_for", "updated_at"])

        self.stdout.write(msg)
        return 1

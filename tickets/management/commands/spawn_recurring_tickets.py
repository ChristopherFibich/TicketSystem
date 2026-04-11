from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from tickets.models import (
    AssignmentMode,
    Completion,
    Ticket,
    TicketStatus,
    TicketTemplate,
)
from tickets.scheduling import next_scheduled_date

User = get_user_model()

# Fairness strategy (v1): balance lifetime completed score so that, over time,
# household members converge toward the same number of tickets done.
#
# Because v1 points are fixed per template, balancing total points and balancing
# completion count are effectively equivalent.


@dataclass(frozen=True)
class Candidate:
    user: User
    weight: int


def choose_assignee(template: TicketTemplate) -> User | None:
    return choose_assignee_with_projected_totals(template, projected_points=None)


def choose_assignee_with_projected_totals(
    template: TicketTemplate,
    projected_points: dict[int, int] | None,
) -> User | None:
    if template.assignment_mode == AssignmentMode.FIXED:
        return template.fixed_assignee

    elig = list(template.eligibilities.select_related("user"))
    candidates = [Candidate(e.user, max(1, int(e.weight))) for e in elig]
    if not candidates:
        return None

    if projected_points is None:
        user_ids = [c.user.id for c in candidates]
        totals = {
            row["completed_by"]: int(row["points"] or 0)
            for row in Completion.objects.filter(completed_by_id__in=user_ids)
            .values("completed_by")
            .annotate(points=Sum("points_awarded"), count=Count("id"))
        }
        projected_points = totals

    best_users: list[Candidate] = []
    best_score: int | None = None

    for c in candidates:
        score = int(projected_points.get(c.user.id, 0))
        if best_score is None or score < best_score:
            best_score = score
            best_users = [c]
        elif score == best_score:
            best_users.append(c)

    if len(best_users) == 1:
        return best_users[0].user

    weights = [c.weight for c in best_users]
    return random.choices([c.user for c in best_users], weights=weights, k=1)[0]


class Command(BaseCommand):
    help = "Spawn tickets from active recurring templates (intended for cron)."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="date", help="Run as if today is YYYY-MM-DD")
        parser.add_argument("--dry-run", action="store_true", help="Show what would happen without creating tickets")
        parser.add_argument("--max-per-template", type=int, default=90, help="Safety limit for catch-up spawning")

    def handle(self, *args, **options):
        if options.get("date"):
            today = date.fromisoformat(options["date"])
        else:
            today = timezone.localdate()

        dry_run: bool = bool(options["dry_run"])
        max_per_template: int = int(options["max_per_template"])

        templates = TicketTemplate.objects.filter(active=True).order_by("id")
        if not templates.exists():
            self.stdout.write("No active templates.")
            return

        # Build a per-run projected total so each new assignment re-balances.
        base_points = {
            row["completed_by"]: int(row["points"] or 0)
            for row in Completion.objects.values("completed_by").annotate(points=Sum("points_awarded"))
        }
        projected_points: dict[int, int] = dict(base_points)

        created_count = 0
        for template in templates:
            created_count += self._spawn_for_template(
                template,
                today=today,
                dry_run=dry_run,
                max_per_template=max_per_template,
                projected_points=projected_points,
            )

        self.stdout.write(self.style.SUCCESS(f"Done. Created {created_count} ticket(s)."))

    def _spawn_for_template(
        self,
        template: TicketTemplate,
        today: date,
        dry_run: bool,
        max_per_template: int,
        projected_points: dict[int, int],
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

        if template.last_completed_for is None:
            next_date = template.start_date
        else:
            next_date = next_scheduled_date(template, template.last_completed_for)
        if next_date > today:
            self.stdout.write(f"[{template.id}] {template.title}: next due {next_date} (not yet)")
            return 0

        if Ticket.objects.filter(template=template, scheduled_for_date=next_date).exists():
            self.stdout.write(f"[{template.id}] {template.title}: already exists for {next_date}")
            return 0

        assignee = choose_assignee_with_projected_totals(template, projected_points=projected_points)
        if template.assignment_mode == AssignmentMode.FIXED and assignee is None:
            raise CommandError(f"Template '{template}' is FIXED but has no fixed_assignee")
        if template.assignment_mode == AssignmentMode.POOL and assignee is None:
            raise CommandError(f"Template '{template}' has no eligible users")

        # Update the per-run projection so the next ticket re-balances.
        if assignee is not None and template.assignment_mode == AssignmentMode.POOL:
            fairness_points = max(1, int(template.points or 1))
            projected_points[assignee.id] = int(projected_points.get(assignee.id, 0)) + fairness_points

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

        self.stdout.write(msg)
        return 1

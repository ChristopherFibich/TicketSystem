from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from tickets.models import AssignmentMode, RecurrenceFrequency, TicketTemplate, TicketTemplateEligibility

User = get_user_model()


class Command(BaseCommand):
    help = "Create a small set of default templates for a 2-person household."

    def add_arguments(self, parser):
        parser.add_argument(
            "--washer",
            required=True,
            help="Username who washes clothes (fixed assignment)",
        )
        parser.add_argument(
            "--folder",
            required=True,
            help="Username who folds clothes (fixed assignment)",
        )

    def handle(self, *args, **options):
        washer = self._get_user(options["washer"])
        folder = self._get_user(options["folder"])

        created = 0
        created += self._get_or_create_template(
            title="Wash clothes",
            description="Run laundry + hang up / dry.",
            frequency=RecurrenceFrequency.WEEKLY,
            interval=1,
            weekly_weekday=5,  # Saturday
            assignment_mode=AssignmentMode.FIXED,
            fixed_assignee=washer,
            points=1,
        )
        created += self._get_or_create_template(
            title="Fold clothes",
            description="Fold and put away clean clothes.",
            frequency=RecurrenceFrequency.WEEKLY,
            interval=1,
            weekly_weekday=6,  # Sunday
            assignment_mode=AssignmentMode.FIXED,
            fixed_assignee=folder,
            points=1,
        )

        kitchen, was_created = TicketTemplate.objects.get_or_create(
            title="Kitchen cleanup",
            defaults={
                "description": "Quick cleanup: surfaces + sink + trash.",
                "active": True,
                "frequency": RecurrenceFrequency.DAILY,
                "interval": 1,
                "assignment_mode": AssignmentMode.POOL,
                "points": 1,
                "counts_for_score": True,
            },
        )
        if was_created:
            created += 1

        for user in [washer, folder]:
            TicketTemplateEligibility.objects.get_or_create(template=kitchen, user=user, defaults={"weight": 1})

        self.stdout.write(self.style.SUCCESS(f"Seeded defaults. Created {created} template(s)."))

    def _get_user(self, username: str):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User '{username}' not found. Create it first in /admin/.") from exc

    def _get_or_create_template(
        self,
        *,
        title: str,
        description: str,
        frequency: str,
        interval: int,
        weekly_weekday: int | None,
        assignment_mode: str,
        fixed_assignee,
        points: int,
    ) -> int:
        _, created = TicketTemplate.objects.get_or_create(
            title=title,
            defaults={
                "description": description,
                "active": True,
                "frequency": frequency,
                "interval": interval,
                "weekly_weekday": weekly_weekday,
                "assignment_mode": assignment_mode,
                "fixed_assignee": fixed_assignee,
                "points": points,
                "counts_for_score": True,
            },
        )
        return 1 if created else 0

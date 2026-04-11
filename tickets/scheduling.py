from __future__ import annotations

from datetime import date, timedelta

from django.core.management.base import CommandError

from .models import RecurrenceFrequency, TicketTemplate


def _add_months(year: int, month: int, months: int) -> tuple[int, int]:
    idx = (month - 1) + months
    return year + (idx // 12), (idx % 12) + 1


def _first_weekday_on_or_after(start: date, weekday: int) -> date:
    delta = (weekday - start.weekday()) % 7
    return start + timedelta(days=delta)


def _next_daily(template: TicketTemplate, after: date) -> date:
    if template.interval < 1:
        raise CommandError(f"Template '{template}' has invalid interval")
    return after + timedelta(days=template.interval)


def _next_weekly(template: TicketTemplate, after: date) -> date:
    if template.interval < 1:
        raise CommandError(f"Template '{template}' has invalid interval")
    return after + timedelta(days=template.interval * 7)


def _next_monthly(template: TicketTemplate, after: date) -> date:
    if template.interval < 1:
        raise CommandError(f"Template '{template}' has invalid interval")

    # Keep the same day-of-month as the completion date (clamped to 28 to avoid invalid dates).
    day = min(after.day, 28)
    y, m = _add_months(after.year, after.month, template.interval)
    return date(y, m, day)


def next_scheduled_date(template: TicketTemplate, after: date) -> date:
    if template.frequency == RecurrenceFrequency.DAILY:
        return _next_daily(template, after)
    if template.frequency == RecurrenceFrequency.WEEKLY:
        return _next_weekly(template, after)
    if template.frequency == RecurrenceFrequency.MONTHLY:
        return _next_monthly(template, after)
    raise CommandError(f"Template '{template}' has unknown frequency '{template.frequency}'")


def next_scheduled_for(template: TicketTemplate) -> date:
    """Return the next scheduled date for a template.

    Uses template.last_completed_for as the reference point; if missing, treats it
    as "not completed yet" (i.e. next is based off start_date).
    """

    last = template.last_completed_for
    if last is None:
        return template.start_date
    return next_scheduled_date(template, last)

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
    next_date = after + timedelta(days=template.interval)
    if next_date < template.start_date:
        return template.start_date
    return next_date


def _next_weekly(template: TicketTemplate, after: date) -> date:
    if template.interval < 1:
        raise CommandError(f"Template '{template}' has invalid interval")

    weekday = template.weekly_weekday
    if weekday is None:
        weekday = template.start_date.weekday()

    first = _first_weekday_on_or_after(template.start_date, weekday)

    base = after + timedelta(days=1)
    candidate = _first_weekday_on_or_after(base, weekday)

    weeks_between = (candidate - first).days // 7
    remainder = weeks_between % template.interval
    if remainder != 0:
        candidate += timedelta(days=(template.interval - remainder) * 7)

    return candidate


def _next_monthly(template: TicketTemplate, after: date) -> date:
    if template.interval < 1:
        raise CommandError(f"Template '{template}' has invalid interval")

    day = template.monthly_day
    if day is None:
        day = min(template.start_date.day, 28)

    first = date(template.start_date.year, template.start_date.month, day)
    if first < template.start_date:
        y, m = _add_months(template.start_date.year, template.start_date.month, 1)
        first = date(y, m, day)

    if after < first:
        return first

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

    Uses template.last_scheduled_for as the reference point; if missing, treats it
    as "not scheduled yet".
    """

    last = template.last_scheduled_for
    if last is None:
        last = template.start_date - timedelta(days=1)
    return next_scheduled_date(template, last)

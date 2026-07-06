from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import AssignmentMode, RecurrenceFrequency, Tag, Ticket, TicketStatus, TicketTemplate


User = get_user_model()


class RecurringTicketSchedulingTests(TestCase):
	def test_spawn_recurring_tickets_keeps_weekly_anchor(self):
		user = User.objects.create_user(username="alice", password="pw")
		template = TicketTemplate.objects.create(
			title="Weekly cleanup",
			description="",
			active=True,
			frequency=RecurrenceFrequency.WEEKLY,
			interval=1,
			start_date=date(2026, 7, 1),
			weekly_weekday=5,
			assignment_mode=AssignmentMode.FIXED,
			fixed_assignee=user,
		)

		call_command("spawn_recurring_tickets", date="2026-07-06")

		ticket = Ticket.objects.get(template=template)
		self.assertEqual(ticket.scheduled_for_date, date(2026, 7, 4))
		template.refresh_from_db()
		self.assertEqual(template.last_scheduled_for, date(2026, 7, 4))

		ticket.status = TicketStatus.DONE
		ticket.save(update_fields=["status", "updated_at"])
		ticket.mark_done(completed_by=user)

		call_command("spawn_recurring_tickets", date="2026-07-13")

		scheduled_dates = list(Ticket.objects.filter(template=template).values_list("scheduled_for_date", flat=True).order_by("scheduled_for_date"))
		self.assertEqual(scheduled_dates, [date(2026, 7, 4), date(2026, 7, 11)])


class GraphsAccessTests(TestCase):
	def test_graphs_requires_graphs_group(self):
		user = User.objects.create_user(username="bob", password="pw")
		self.client.force_login(user)

		response = self.client.get(reverse("graphs"))

		self.assertRedirects(response, reverse("dashboard"))

	def test_graphs_allows_graphs_group_members(self):
		user = User.objects.create_user(username="alice", password="pw")
		group = Group.objects.get(name="Graphs")
		user.groups.add(group)
		self.client.force_login(user)

		response = self.client.get(reverse("graphs"))

		self.assertEqual(response.status_code, 200)

	def test_graphs_link_shows_in_nav_for_graphs_group_members(self):
		user = User.objects.create_user(username="alice", password="pw")
		group = Group.objects.get(name="Graphs")
		user.groups.add(group)
		self.client.force_login(user)

		response = self.client.get(reverse("dashboard"))

		self.assertContains(response, reverse("graphs"))


class DailyTicketsViewTests(TestCase):
	def test_daily_view_shows_only_daily_tagged_tickets(self):
		alice = User.objects.create_user(username="alice", password="pw")
		bob = User.objects.create_user(username="bob", password="pw")
		daily = Tag.objects.create(name="Daily")
		other = Tag.objects.create(name="Other")

		daily_one = Ticket.objects.create(title="Daily one", assignee=alice, created_by=alice)
		daily_one.tags.add(daily)
		daily_two = Ticket.objects.create(title="Daily two", assignee=bob, created_by=alice)
		daily_two.tags.add(daily)
		not_daily = Ticket.objects.create(title="Not daily", assignee=bob, created_by=alice)
		not_daily.tags.add(other)

		self.client.force_login(alice)
		response = self.client.get(reverse("daily_tickets"))

		self.assertContains(response, "Daily one")
		self.assertContains(response, "Daily two")
		self.assertNotContains(response, "Not daily")
		self.assertContains(response, "For alice")
		self.assertContains(response, "For bob")
		self.assertContains(response, "0d old")

		tickets = list(response.context["tickets"])
		self.assertEqual(len(tickets), 2)
		self.assertNotEqual(tickets[0].card_bg, tickets[1].card_bg)


class TicketListSplitTests(TestCase):
	def test_todo_excludes_daily_and_all_includes_everything(self):
		user = User.objects.create_user(username="alice", password="pw")
		daily = Tag.objects.create(name="Daily")
		other = Tag.objects.create(name="Other")

		daily_ticket = Ticket.objects.create(title="Daily task", assignee=user, created_by=user)
		daily_ticket.tags.add(daily)
		normal_ticket = Ticket.objects.create(title="Normal task", assignee=user, created_by=user)
		normal_ticket.tags.add(other)

		self.client.force_login(user)

		todo_response = self.client.get(reverse("todo_tickets"))
		self.assertContains(todo_response, "Normal task")
		self.assertNotContains(todo_response, "Daily task")

		all_response = self.client.get(reverse("all_tickets"))
		self.assertContains(all_response, "Normal task")
		self.assertContains(all_response, "Daily task")
		self.assertContains(all_response, "0d old")


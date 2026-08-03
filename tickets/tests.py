from datetime import date
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from .admin import TicketTemplateAdmin
from .forms import TicketUpdateForm
from .models import AssignmentMode, RecurrenceFrequency, Tag, Ticket, TicketChecklistItem, TicketPriority, TicketStatus, TicketTemplate, UserAvailability


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

	def test_recreate_daily_resets_and_respawns_daily_templates(self):
		user = User.objects.create_user(username="alice", password="pw")
		template = TicketTemplate.objects.create(
			title="Daily cleanup",
			description="",
			active=True,
			frequency=RecurrenceFrequency.DAILY,
			interval=1,
			start_date=date(2026, 7, 1),
			assignment_mode=AssignmentMode.FIXED,
			fixed_assignee=user,
		)
		daily_tag = Tag.objects.create(name="Daily")
		template.tags.add(daily_tag)

		call_command("spawn_recurring_tickets", date="2026-07-01")
		first_ticket = Ticket.objects.get(template=template)
		self.assertEqual(first_ticket.scheduled_for_date, date(2026, 7, 1))

		call_command("spawn_recurring_tickets", date="2026-07-01", recreate_daily=True)

		tickets = list(Ticket.objects.filter(template=template).order_by("scheduled_for_date", "id"))
		self.assertEqual([ticket.scheduled_for_date for ticket in tickets], [date(2026, 7, 1)])
		template.refresh_from_db()
		self.assertEqual(template.last_scheduled_for, date(2026, 7, 1))

	def test_household_fairness_ignores_todo_completions(self):
		user_one = User.objects.create_user(username="alice", password="pw")
		user_two = User.objects.create_user(username="bob", password="pw")
		pool_template = TicketTemplate.objects.create(
			title="Household cleanup",
			description="",
			active=True,
			frequency=RecurrenceFrequency.DAILY,
			interval=1,
			start_date=date(2026, 7, 1),
			assignment_mode=AssignmentMode.POOL,
			points=1,
		)
		daily_tag = Tag.objects.create(name="Daily")
		pool_template.tags.add(daily_tag)
		pool_template.eligibilities.create(user=user_one, weight=1)
		pool_template.eligibilities.create(user=user_two, weight=1)

		todo_template = TicketTemplate.objects.create(
			title="Todo task",
			description="",
			active=True,
			frequency=RecurrenceFrequency.DAILY,
			interval=1,
			start_date=date(2026, 7, 1),
			assignment_mode=AssignmentMode.FIXED,
			fixed_assignee=user_one,
			points=2,
		)
		todo_ticket = Ticket.objects.create(
			template=todo_template,
			title="Todo task",
			description="",
			status=TicketStatus.NEW,
			assignee=user_one,
			counts_for_score=True,
		)
		todo_ticket.mark_done(completed_by=user_one)

		household_ticket = Ticket.objects.create(
			template=pool_template,
			title="Household done",
			description="",
			status=TicketStatus.NEW,
			assignee=user_two,
			counts_for_score=True,
		)
		household_ticket.tags.add(daily_tag)
		household_ticket.mark_done(completed_by=user_two)

		with patch("tickets.management.commands.spawn_recurring_tickets.random.choices", return_value=[user_two]):
			call_command("spawn_recurring_tickets", date="2026-07-07")

		spawned = Ticket.objects.get(template=pool_template, scheduled_for_date=date(2026, 7, 7))
		self.assertEqual(spawned.assignee, user_two)

	def test_pool_assignment_skips_absent_users(self):
		present = User.objects.create_user(username="alice", password="pw")
		absent = User.objects.create_user(username="bob", password="pw")
		UserAvailability.objects.create(user=absent, is_absent=True)
		template = TicketTemplate.objects.create(
			title="Pool task",
			description="",
			active=True,
			frequency=RecurrenceFrequency.DAILY,
			interval=1,
			start_date=date(2026, 7, 1),
			assignment_mode=AssignmentMode.POOL,
			points=1,
		)
		template.eligibilities.create(user=present, weight=1)
		template.eligibilities.create(user=absent, weight=1)

		call_command("spawn_recurring_tickets", date="2026-07-01")

		ticket = Ticket.objects.get(template=template)
		self.assertEqual(ticket.assignee, present)


class TicketTemplateAdminDefaultsTests(TestCase):
	def test_pool_add_form_defaults_to_all_active_users(self):
		request_factory = RequestFactory()
		request = request_factory.get("/admin/tickets/tickettemplate/add/")

		superuser = User.objects.create_superuser(username="admin", email="admin@example.com", password="pw")
		alice = User.objects.create_user(username="alice", password="pw")
		bob = User.objects.create_user(username="bob", password="pw", is_active=False)

		request.user = superuser
		admin_instance = TicketTemplateAdmin(TicketTemplate, admin.site)
		inline = admin_instance.get_inline_instances(request)[0]

		formset_kwargs = admin_instance.get_formset_kwargs(request, None, inline, "eligibilities")

		self.assertEqual(len(formset_kwargs["initial"]), 2)
		self.assertCountEqual(
			[row["user"] for row in formset_kwargs["initial"]],
			[superuser.pk, alice.pk],
		)


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


class AbwesendToggleTests(TestCase):
	def test_abwesend_toggle_flips_presence_and_exposes_context(self):
		user = User.objects.create_user(username="alice", password="pw")
		self.client.force_login(user)

		response = self.client.get(reverse("dashboard"))
		self.assertFalse(response.context["is_abwesend"])
		self.assertContains(response, "abwesend")

		response = self.client.post(reverse("abwesend_toggle"), {"next": reverse("dashboard")})
		self.assertRedirects(response, reverse("dashboard"))
		self.assertTrue(UserAvailability.objects.get(user=user).is_absent)

		response = self.client.get(reverse("dashboard"))
		self.assertTrue(response.context["is_abwesend"])

		response = self.client.post(reverse("abwesend_toggle"), {"next": reverse("dashboard")})
		self.assertRedirects(response, reverse("dashboard"))
		self.assertFalse(UserAvailability.objects.get(user=user).is_absent)


class HaushaltTicketsViewTests(TestCase):
	def test_haushalt_view_shows_daily_weekly_and_monthly_tagged_tickets(self):
		alice = User.objects.create_user(username="alice", password="pw")
		bob = User.objects.create_user(username="bob", password="pw")
		daily = Tag.objects.create(name="Daily")
		weekly = Tag.objects.create(name="Weekly")
		monthly = Tag.objects.create(name="Monthly")
		other = Tag.objects.create(name="Other")

		daily_one = Ticket.objects.create(title="Daily one", assignee=alice, created_by=alice)
		daily_one.tags.add(daily)
		weekly_one = Ticket.objects.create(title="Weekly one", assignee=bob, created_by=alice)
		weekly_one.tags.add(weekly)
		monthly_one = Ticket.objects.create(title="Monthly one", assignee=alice, created_by=alice)
		monthly_one.tags.add(monthly)
		not_household = Ticket.objects.create(title="Not household", assignee=bob, created_by=alice)
		not_household.tags.add(other)

		self.client.force_login(alice)
		response = self.client.get(reverse("haushalt_tickets"))

		self.assertContains(response, "Daily one")
		self.assertContains(response, "Weekly one")
		self.assertContains(response, "Monthly one")
		self.assertNotContains(response, "Not household")
		self.assertContains(response, "For alice")
		self.assertContains(response, "For bob")
		self.assertContains(response, "0d old")

		tickets = list(response.context["tickets"])
		self.assertEqual(len(tickets), 3)
		self.assertNotEqual(tickets[0].card_bg, tickets[1].card_bg)


class TicketListSplitTests(TestCase):
	def test_todo_excludes_daily_and_all_includes_everything(self):
		user = User.objects.create_user(username="alice", password="pw")
		daily = Tag.objects.create(name="Daily")
		weekly = Tag.objects.create(name="Weekly")
		monthly = Tag.objects.create(name="Monthly")
		other = Tag.objects.create(name="Other")

		daily_ticket = Ticket.objects.create(title="Daily task", assignee=user, created_by=user)
		daily_ticket.tags.add(daily)
		weekly_ticket = Ticket.objects.create(title="Weekly task", assignee=user, created_by=user)
		weekly_ticket.tags.add(weekly)
		monthly_ticket = Ticket.objects.create(title="Monthly task", assignee=user, created_by=user)
		monthly_ticket.tags.add(monthly)
		normal_ticket = Ticket.objects.create(title="Normal task", assignee=user, created_by=user)
		normal_ticket.tags.add(other)

		self.client.force_login(user)

		todo_response = self.client.get(reverse("todo_tickets"))
		self.assertContains(todo_response, "Normal task")
		self.assertNotContains(todo_response, "Daily task")
		self.assertNotContains(todo_response, "Weekly task")
		self.assertNotContains(todo_response, "Monthly task")

		all_response = self.client.get(reverse("all_tickets"))
		self.assertContains(all_response, "Normal task")
		self.assertContains(all_response, "Daily task")
		self.assertContains(all_response, "Weekly task")
		self.assertContains(all_response, "Monthly task")
		self.assertContains(all_response, "0d old")

	def test_todo_groups_tickets_by_priority(self):
		user = User.objects.create_user(username="alice", password="pw")
		low = Ticket.objects.create(title="Low task", assignee=user, created_by=user, priority=TicketPriority.LOW)
		med = Ticket.objects.create(title="Med task", assignee=user, created_by=user, priority=TicketPriority.MED)
		high = Ticket.objects.create(title="High task", assignee=user, created_by=user, priority=TicketPriority.HIGH)

		self.client.force_login(user)
		response = self.client.get(reverse("todo_tickets"))

		self.assertContains(response, "Low")
		self.assertContains(response, "Med")
		self.assertContains(response, "High")
		self.assertContains(response, "Low task")
		self.assertContains(response, "Med task")
		self.assertContains(response, "High task")
		sections = response.context["sections"]
		self.assertEqual([section["label"] for section in sections], ["Low", "Med", "High"])
		self.assertEqual([section["count"] for section in sections], [1, 1, 1])

	def test_blank_priority_falls_back_to_med(self):
		user = User.objects.create_user(username="alice", password="pw")
		ticket = Ticket.objects.create(title="Unprioritized task", assignee=user, created_by=user, priority=TicketPriority.LOW)
		Ticket.objects.filter(pk=ticket.pk).update(priority="")

		self.client.force_login(user)
		response = self.client.get(reverse("todo_tickets"))

		self.assertContains(response, "Unprioritized task")
		sections = response.context["sections"]
		self.assertEqual([section["count"] for section in sections], [0, 1, 0])


class TicketPriorityFormTests(TestCase):
	def test_ticket_update_form_persists_priority(self):
		user = User.objects.create_user(username="alice", password="pw")
		ticket = Ticket.objects.create(title="Priority task", assignee=user, created_by=user)

		form = TicketUpdateForm(
			data={
				"title": "Priority task",
				"description": "",
				"assignee": user.pk,
				"status": TicketStatus.NEW,
				"priority": TicketPriority.HIGH,
				"counts_for_score": True,
				"tags": [],
			},
			instance=ticket,
		)

		self.assertTrue(form.is_valid())
		updated = form.save()
		self.assertEqual(updated.priority, TicketPriority.HIGH)


class TicketChecklistTests(TestCase):
	def test_ticket_detail_adds_and_toggles_checklist_items(self):
		user = User.objects.create_user(username="alice", password="pw")
		ticket = Ticket.objects.create(title="Checklist task", assignee=user, created_by=user)
		self.client.force_login(user)

		response = self.client.post(reverse("ticket_detail", args=[ticket.pk]), {"add_checklist_item": "1", "checklist_text": "Subtask one"})
		self.assertRedirects(response, reverse("ticket_detail", args=[ticket.pk]))
		item = TicketChecklistItem.objects.get(ticket=ticket)
		self.assertEqual(item.text, "Subtask one")
		self.assertFalse(item.is_done)

		response = self.client.post(
			reverse("ticket_detail", args=[ticket.pk]),
			{"save_checklist_item": "1", "checklist_item_id": item.pk, "is_done": "on"},
		)
		self.assertRedirects(response, reverse("ticket_detail", args=[ticket.pk]))
		item.refresh_from_db()
		self.assertTrue(item.is_done)


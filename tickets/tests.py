from datetime import date

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from .admin import TicketTemplateAdmin
from .forms import TicketUpdateForm
from .models import AssignmentMode, RecurrenceFrequency, Tag, Ticket, TicketPriority, TicketStatus, TicketTemplate


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


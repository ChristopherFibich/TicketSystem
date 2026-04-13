from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import TicketForm
from .models import Completion, FeedTime, PetFeedStatus, PetType, Tag, Ticket, TicketStatus

AuthUser = get_user_model()


def _ticket_bg_class(ticket: Ticket, now) -> str:
	if ticket.status == TicketStatus.DONE:
		return "list-group-item-primary"

	start = ticket.assigned_at or ticket.created_at
	if start is None:
		return ""

	age_days = (now - start).total_seconds() / 86400
	if age_days < 1:
		return "list-group-item-success"
	if age_days < 5:
		return "list-group-item-warning"
	return "list-group-item-danger"


def home(request: HttpRequest) -> HttpResponse:
	if request.user.is_authenticated:
		return redirect("my_tickets")
	return redirect("login")


@login_required
def my_tickets(request: HttpRequest) -> HttpResponse:
	now = timezone.now()
	tickets = (
		Ticket.objects.select_related("assignee", "template")
		.filter(assignee=request.user)
		.order_by("status", "-created_at")
	)

	grouped: dict[str, list[Ticket]] = {
		TicketStatus.NEW: [],
		TicketStatus.DOING: [],
		TicketStatus.DONE: [],
	}
	for ticket in tickets:
		ticket.bg_class = _ticket_bg_class(ticket, now)

		grouped[ticket.status].append(ticket)

	sections = []
	for status in [TicketStatus.NEW, TicketStatus.DOING, TicketStatus.DONE]:
		items = grouped.get(status, [])
		sections.append({"status": status, "label": status.label, "tickets": items, "count": len(items)})

	return render(request, "tickets/my_tickets.html", {"sections": sections})


@login_required
def ticket_create(request: HttpRequest) -> HttpResponse:
	if request.method == "POST":
		form = TicketForm(request.POST)
		if form.is_valid():
			ticket = form.save(commit=False)
			ticket.created_by = request.user
			if ticket.assignee_id is None:
				ticket.assignee = request.user
			ticket.save()
			return redirect("ticket_detail", pk=ticket.pk)
	else:
		form = TicketForm(initial={"assignee": request.user, "status": TicketStatus.NEW})

	return render(request, "tickets/ticket_form.html", {"form": form, "mode": "create"})


@login_required
def ticket_detail(request: HttpRequest, pk: int) -> HttpResponse:
	ticket = get_object_or_404(Ticket.objects.select_related("assignee", "template"), pk=pk)
	existing_completion_user_ids = list(ticket.completions.values_list("completed_by_id", flat=True))

	if request.method == "POST":
		if "share_points" in request.POST:
			if ticket.status != TicketStatus.DONE:
				return redirect("ticket_detail", pk=ticket.pk)

			share_user_ids = [int(x) for x in request.POST.getlist("share_users") if str(x).isdigit()]
			share_user_ids = [uid for uid in share_user_ids if uid not in existing_completion_user_ids]
			if share_user_ids:
				# Award the same points as the ticket completion to each selected user.
				now = timezone.now()
				points = 1
				if ticket.template_id and ticket.template:
					if ticket.template.counts_for_score:
						points = int(ticket.template.points or 1)
					else:
						points = 0
				else:
					points = 1 if ticket.counts_for_score else 0

				completed_at = ticket.completed_at or now
				time_to_complete_seconds = None
				if ticket.created_at:
					delta = completed_at - ticket.created_at
					time_to_complete_seconds = max(0, int(delta.total_seconds()))

				users = AuthUser.objects.filter(id__in=share_user_ids, is_active=True)
				for u in users:
					Completion.objects.get_or_create(
						ticket=ticket,
						completed_by=u,
						defaults={
							"completed_at": completed_at,
							"points_awarded": points,
							"time_to_complete_seconds": time_to_complete_seconds,
						},
					)
			return redirect("ticket_detail", pk=ticket.pk)

		if "take_over" in request.POST:
			if ticket.status != TicketStatus.DONE:
				ticket.assignee = request.user
				ticket.save(update_fields=["assignee", "assigned_at", "updated_at"])
			return redirect("ticket_detail", pk=ticket.pk)

		if "mark_done" in request.POST:
			ticket.mark_done(completed_by=request.user)
			return redirect("ticket_detail", pk=ticket.pk)

		prev_status = ticket.status
		form = TicketForm(request.POST, instance=ticket)
		if form.is_valid():
			ticket = form.save()
			if prev_status != TicketStatus.DONE and ticket.status == TicketStatus.DONE:
				ticket.mark_done(completed_by=request.user)
			return redirect("ticket_detail", pk=ticket.pk)
	else:
		form = TicketForm(instance=ticket)

	completions = list(ticket.completions.select_related("completed_by").order_by("completed_at"))
	completion = completions[0] if completions else None
	share_candidates = AuthUser.objects.filter(is_active=True).exclude(id__in=existing_completion_user_ids).order_by("username")
	return render(
		request,
		"tickets/ticket_detail.html",
		{
			"ticket": ticket,
			"form": form,
			"completion": completion,
			"completions": completions,
			"share_candidates": share_candidates,
		},
	)


@login_required
def all_tickets(request: HttpRequest) -> HttpResponse:
	now = timezone.now()
	q = (request.GET.get("q") or "").strip()
	show_done = (request.GET.get("show_done") or "").strip() in {"1", "true", "yes", "on"}

	tickets = (
		Ticket.objects.select_related("assignee", "template")
		.prefetch_related("tags")
		.all()
		.order_by("status", "-created_at")
	)
	if not show_done:
		tickets = tickets.exclude(status=TicketStatus.DONE)
	if q:
		tickets = tickets.filter(
			Q(title__icontains=q)
			| Q(description__icontains=q)
			| Q(assignee__username__icontains=q)
			| Q(template__title__icontains=q)
			| Q(tags__name__icontains=q)
		).distinct()
	for ticket in tickets:
		ticket.bg_class = _ticket_bg_class(ticket, now)

	return render(
		request,
		"tickets/all_tickets.html",
		{
			"tickets": tickets,
			"q": q,
			"show_done": show_done,
		},
	)


@login_required
def help_page(request: HttpRequest) -> HttpResponse:
	return render(request, "tickets/help.html")


@login_required
def pets(request: HttpRequest) -> HttpResponse:
	today = timezone.localdate()

	def _get_row(pet: str, time: str) -> PetFeedStatus:
		obj, _ = PetFeedStatus.objects.get_or_create(day=today, pet=pet, time=time, defaults={"fed": False})
		return obj

	if request.method == "POST":
		pet = (request.POST.get("pet") or "").strip()
		time = (request.POST.get("time") or "").strip()
		if pet in {PetType.CAT, PetType.DOG} and time in {FeedTime.MORNING, FeedTime.EVENING}:
			row = _get_row(pet, time)
			row.fed = not bool(row.fed)
			row.updated_by = request.user
			row.save(update_fields=["fed", "updated_by", "updated_at"])
		return redirect("pets")

	cat_morning = _get_row(PetType.CAT, FeedTime.MORNING)
	cat_evening = _get_row(PetType.CAT, FeedTime.EVENING)
	dog_morning = _get_row(PetType.DOG, FeedTime.MORNING)
	dog_evening = _get_row(PetType.DOG, FeedTime.EVENING)

	return render(
		request,
		"tickets/pets.html",
		{
			"today": today,
			"cat_morning": cat_morning,
			"cat_evening": cat_evening,
			"dog_morning": dog_morning,
			"dog_evening": dog_evening,
		},
	)


@login_required
def scoreboard(request: HttpRequest) -> HttpResponse:
	users = User.objects.all().order_by("username")

	totals = {
		row["completed_by"]: row
		for row in Completion.objects.values("completed_by")
		.annotate(points=Sum("points_awarded"), avg_seconds=Avg("time_to_complete_seconds"))
	}

	since = timezone.now() - timedelta(days=30)
	recent = {
		row["completed_by"]: row
		for row in Completion.objects.filter(completed_at__gte=since)
		.values("completed_by")
		.annotate(points=Sum("points_awarded"))
	}

	today = timezone.localdate()
	since_7d = timezone.now() - timedelta(days=7)
	since_30d = timezone.now() - timedelta(days=30)

	points_today = {
		row["completed_by"]: int(row["points"] or 0)
		for row in Completion.objects.filter(completed_at__date=today)
		.values("completed_by")
		.annotate(points=Sum("points_awarded"))
	}
	points_7d = {
		row["completed_by"]: int(row["points"] or 0)
		for row in Completion.objects.filter(completed_at__gte=since_7d)
		.values("completed_by")
		.annotate(points=Sum("points_awarded"))
	}
	points_30d = {
		row["completed_by"]: int(row["points"] or 0)
		for row in Completion.objects.filter(completed_at__gte=since_30d)
		.values("completed_by")
		.annotate(points=Sum("points_awarded"))
	}

	rows = []
	for user in users:
		total = totals.get(user.id, {})
		last30 = recent.get(user.id, {})
		p_today = points_today.get(user.id, 0)
		p_7d = points_7d.get(user.id, 0)
		p_30d = points_30d.get(user.id, 0)
		rows.append(
			{
				"user": user,
				"points_total": total.get("points") or 0,
				"avg_seconds": total.get("avg_seconds"),
				"points_30d": last30.get("points") or 0,
				"points_today": p_today,
				"points_7d": p_7d,
				"points_30d_window": p_30d,
				"done_items": [],
			}
		)

	rows.sort(key=lambda r: (r["points_total"],), reverse=True)

	max_today = max([r["points_today"] for r in rows] + [0])
	max_7d = max([r["points_7d"] for r in rows] + [0])
	max_30d = max([r["points_30d_window"] for r in rows] + [0])

	def _pct(value: int, max_value: int) -> int:
		if max_value <= 0:
			return 0
		return int(round((value / max_value) * 100))

	charts = {
		"today": {
			"title": "Today",
			"max": max_today,
			"key": "points_today",
		},
		"week": {
			"title": "Last 7 days",
			"max": max_7d,
			"key": "points_7d",
		},
		"month": {
			"title": "Last 30 days",
			"max": max_30d,
			"key": "points_30d_window",
		},
	}

	for r in rows:
		r["pct_today"] = _pct(r["points_today"], max_today)
		r["pct_7d"] = _pct(r["points_7d"], max_7d)
		r["pct_30d"] = _pct(r["points_30d_window"], max_30d)

	# Build a bounded list of completed ticket titles per user for display.
	# Keep it capped to avoid unbounded page sizes over time.
	max_items_per_user = 200
	done_items_by_user_id: dict[int, list[dict]] = {r["user"].id: [] for r in rows}

	for completion in (
		Completion.objects.select_related("ticket", "completed_by").order_by("-completed_at").iterator()
	):
		user_id = completion.completed_by_id
		items = done_items_by_user_id.get(user_id)
		if items is None or len(items) >= max_items_per_user:
			continue
		items.append(
			{
				"title": completion.ticket.title,
				"points": completion.points_awarded,
				"completed_at": completion.completed_at,
			}
		)

		# Early exit if everyone is full.
		if all(len(v) >= max_items_per_user for v in done_items_by_user_id.values()):
			break

	for r in rows:
		r["done_items"] = done_items_by_user_id.get(r["user"].id, [])

	# Monthly history (bounded to keep the page size reasonable).
	max_months = 24
	monthly_scores: dict[object, dict[int, int]] = {}
	month_order: list[object] = []

	for row in (
		Completion.objects.annotate(month=TruncMonth("completed_at"))
		.values("month", "completed_by")
		.annotate(points=Sum("points_awarded"))
		.order_by("-month")
	):
		month = row["month"]
		if month not in monthly_scores:
			if len(month_order) >= max_months:
				break
			monthly_scores[month] = {}
			month_order.append(month)

		monthly_scores[month][int(row["completed_by"])] = int(row["points"] or 0)

	month_history = []
	months_won_by_user_id: dict[int, int] = {u.id: 0 for u in users}
	for month in month_order:
		scores = []
		max_points = 0
		for user in users:
			points = monthly_scores.get(month, {}).get(user.id, 0)
			max_points = max(max_points, points)
			scores.append({"user_id": user.id, "username": user.username, "points": points})

		# Mark winner(s) for display; avoid highlighting when everyone has 0.
		for s in scores:
			s["is_winner"] = bool(max_points > 0 and s["points"] == max_points)
			if s["is_winner"]:
				# Count ties as a win for each top scorer.
				months_won_by_user_id[int(s["user_id"])] = months_won_by_user_id.get(int(s["user_id"]), 0) + 1
		month_history.append({"month": month, "scores": scores})

	months_won = [{"username": u.username, "count": months_won_by_user_id.get(u.id, 0)} for u in users]

	# Per-tag breakdown (based on completed tickets).
	tags = list(Tag.objects.all().order_by("name"))
	tag_counts: dict[int, dict[int, int]] = {t.id: {} for t in tags}

	for row in (
		Completion.objects.filter(ticket__tags__isnull=False)
		.values("ticket__tags", "completed_by")
		.annotate(count=Count("id"))
	):
		tag_id = int(row["ticket__tags"])
		user_id = int(row["completed_by"])
		if tag_id not in tag_counts:
			continue
		tag_counts[tag_id][user_id] = int(row["count"] or 0)

	tag_stats = []
	for tag in tags:
		counts_by_user = tag_counts.get(tag.id, {})
		total = sum(counts_by_user.get(u.id, 0) for u in users)
		max_count = max([counts_by_user.get(u.id, 0) for u in users] + [0])

		rows_for_tag = []
		for u in users:
			count = counts_by_user.get(u.id, 0)
			pct = 0 if total <= 0 else int(round((count / total) * 100))
			rows_for_tag.append(
				{
					"username": u.username,
					"count": count,
					"pct": pct,
					"is_winner": bool(max_count > 0 and count == max_count),
				}
			)

		tag_stats.append({"tag": tag.name, "rows": rows_for_tag, "total": total})

	return render(
		request,
		"tickets/scoreboard.html",
		{
			"rows": rows,
			"charts": charts,
			"month_history": month_history,
			"months_won": months_won,
			"tag_stats": tag_stats,
		},
	)

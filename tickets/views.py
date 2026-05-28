from datetime import date, timedelta
import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import TicketCreateForm, TicketUpdateForm
from .models import (
	Completion,
	DashboardToggle,
	DashboardToggleGroup,
	DashboardToggleStatus,
	DashboardWidget,
	DashboardWidgetKind,
	AssignmentMode,
	FeedTime,
	PetFeedStatus,
	PetType,
	ShoppingItem,
	Tag,
	Ticket,
	TicketTemplate,
	TicketStatus,
	WeightEntry,
)

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
		return redirect("dashboard")
	return redirect("login")


@login_required
def my_tickets(request: HttpRequest) -> HttpResponse:
	now = timezone.now()
	q = (request.GET.get("q") or "").strip()
	show_done_param = (request.GET.get("show_done") or "").strip()
	# My tickets historically showed DONE; default to showing it.
	show_done = True if show_done_param == "" else show_done_param in {"1", "true", "yes", "on"}
	tickets = (
		Ticket.objects.select_related("assignee", "template")
		.prefetch_related("tags")
		.filter(assignee=request.user)
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

	grouped: dict[str, list[Ticket]] = {
		TicketStatus.NEW: [],
		TicketStatus.DOING: [],
		TicketStatus.DONE: [],
	}
	for ticket in tickets:
		ticket.bg_class = _ticket_bg_class(ticket, now)

		grouped[ticket.status].append(ticket)

	sections = []
	statuses = [TicketStatus.NEW, TicketStatus.DOING, TicketStatus.DONE] if show_done else [TicketStatus.NEW, TicketStatus.DOING]
	for status in statuses:
		items = grouped.get(status, [])
		sections.append({"status": status, "label": status.label, "tickets": items, "count": len(items)})

	return render(
		request,
		"tickets/my_tickets.html",
		{
			"sections": sections,
			"q": q,
			"show_done": show_done,
		},
	)


@login_required
def ticket_create(request: HttpRequest) -> HttpResponse:
	selected_template = None
	selected_template_id = (request.GET.get("template") or "").strip()
	if selected_template_id.isdigit():
		selected_template = TicketTemplate.objects.filter(active=True, id=int(selected_template_id)).first()

	def _initial_from_template(tpl: TicketTemplate | None):
		initial = {"assignee": request.user, "status": TicketStatus.NEW}
		if tpl:
			initial.update(
				{
					"template": tpl.id,
					"title": tpl.title,
					"description": tpl.description,
					"counts_for_score": tpl.counts_for_score,
					"tags": list(tpl.tags.values_list("id", flat=True)),
				}
			)
			if tpl.assignment_mode == AssignmentMode.FIXED and tpl.fixed_assignee_id:
				initial["assignee"] = tpl.fixed_assignee_id
		return initial

	if request.method == "POST":
		if "load_template" in request.POST:
			template_id = (request.POST.get("template") or "").strip()
			tpl = None
			if template_id.isdigit():
				tpl = TicketTemplate.objects.filter(active=True, id=int(template_id)).first()
			form = TicketCreateForm(initial=_initial_from_template(tpl))
			return render(request, "tickets/ticket_form.html", {"form": form, "mode": "create"})

		form = TicketCreateForm(request.POST)
		if form.is_valid():
			ticket = form.save(commit=False)
			ticket.created_by = request.user
			if ticket.assignee_id is None:
				ticket.assignee = request.user
			ticket.save()
			form.save_m2m()
			# If created from a template and no tags were selected, inherit template tags.
			if ticket.template_id and ticket.tags.count() == 0:
				ticket.tags.set(ticket.template.tags.all())
			return redirect("ticket_detail", pk=ticket.pk)
	else:
		form = TicketCreateForm(initial=_initial_from_template(selected_template))

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
		form = TicketUpdateForm(request.POST, instance=ticket)
		if form.is_valid():
			ticket = form.save()
			if prev_status != TicketStatus.DONE and ticket.status == TicketStatus.DONE:
				ticket.mark_done(completed_by=request.user)
			return redirect("ticket_detail", pk=ticket.pk)
	else:
		form = TicketUpdateForm(instance=ticket)

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

def dashboard(request: HttpRequest) -> HttpResponse:
	today = timezone.localdate()
	widgets = list(DashboardWidget.objects.filter(enabled=True).order_by("order", "id"))
	if not widgets:
		widgets = [
			DashboardWidget(kind=DashboardWidgetKind.PET_FEED, title="", order=10, enabled=True),
			DashboardWidget(kind=DashboardWidgetKind.TOGGLES, title="", order=20, enabled=True),
		]
	widget_kinds = {w.kind for w in widgets}

	def _get_row(pet: str, time: str) -> PetFeedStatus:
		obj, _ = PetFeedStatus.objects.get_or_create(day=today, pet=pet, time=time, defaults={"fed": False})
		return obj

	def _get_toggle_status(toggle_id: int) -> DashboardToggleStatus | None:
		if toggle_id <= 0:
			return None
		return DashboardToggleStatus.objects.filter(day=today, toggle_id=toggle_id).select_related("toggle").first()

	if request.method == "POST":
		pet = (request.POST.get("pet") or "").strip()
		time = (request.POST.get("time") or "").strip()
		toggle_id_raw = (request.POST.get("toggle_id") or "").strip()

		if pet and time:
			if pet in {PetType.CAT, PetType.DOG} and time in {FeedTime.MORNING, FeedTime.EVENING}:
				row = _get_row(pet, time)
				row.fed = not bool(row.fed)
				row.updated_by = request.user
				row.save(update_fields=["fed", "updated_by", "updated_at"])
			return redirect("dashboard")

		if toggle_id_raw.isdigit():
			toggle_id = int(toggle_id_raw)
			if not DashboardToggle.objects.filter(id=toggle_id, enabled=True, group__enabled=True).exists():
				return redirect("dashboard")
			row = _get_toggle_status(toggle_id)
			if row is None:
				# Create new status row (toggle exists check is implied by FK on create).
				row = DashboardToggleStatus.objects.create(day=today, toggle_id=toggle_id, on=True, updated_by=request.user)
			else:
				row.on = not bool(row.on)
				row.updated_by = request.user
				row.save(update_fields=["on", "updated_by", "updated_at"])
			return redirect("dashboard")

		return redirect("dashboard")

	cat_morning = cat_evening = dog_morning = dog_evening = None
	if DashboardWidgetKind.PET_FEED in widget_kinds:
		cat_morning = _get_row(PetType.CAT, FeedTime.MORNING)
		cat_evening = _get_row(PetType.CAT, FeedTime.EVENING)
		dog_morning = _get_row(PetType.DOG, FeedTime.MORNING)
		dog_evening = _get_row(PetType.DOG, FeedTime.EVENING)

	toggle_groups = []
	status_by_toggle_id: dict[int, DashboardToggleStatus] = {}
	if DashboardWidgetKind.TOGGLES in widget_kinds:
		toggle_groups = list(
			DashboardToggleGroup.objects.filter(enabled=True)
			.prefetch_related("toggles")
			.order_by("order", "id")
		)
		show_30d_stats = any(
			w.kind == DashboardWidgetKind.TOGGLES and bool(getattr(w, "toggles_show_30d_stats", False)) for w in widgets
		)
		toggle_ids = []
		for group in toggle_groups:
			group.enabled_toggles = [t for t in list(group.toggles.all().order_by("order", "id")) if t.enabled]
			toggle_ids.extend([t.id for t in group.enabled_toggles])
		if toggle_ids:
			statuses = DashboardToggleStatus.objects.filter(day=today, toggle_id__in=toggle_ids).select_related("toggle")
			status_by_toggle_id = {s.toggle_id: s for s in statuses}

		last30_on_by_toggle_id: dict[int, int] = {}
		if show_30d_stats and toggle_ids:
			start_day = today - timedelta(days=29)
			rows = (
				DashboardToggleStatus.objects.filter(
					day__gte=start_day,
					day__lte=today,
					toggle_id__in=toggle_ids,
					on=True,
				)
				.values("toggle_id")
				.annotate(c=Count("id"))
			)
			last30_on_by_toggle_id = {r["toggle_id"]: int(r["c"] or 0) for r in rows}
			last30_total = 30
		for group in toggle_groups:
			for t in getattr(group, "enabled_toggles", []):
				s = status_by_toggle_id.get(t.id)
				t.is_on = bool(s.on) if s else False
				if show_30d_stats:
					t.last30_on = last30_on_by_toggle_id.get(t.id, 0)
					t.last30_total = last30_total

	shopping_items = []
	shopping_count_total = 0
	shopping_count_open = 0
	if DashboardWidgetKind.SHOPPING_PREVIEW in widget_kinds:
		shopping_count_total = ShoppingItem.objects.count()
		shopping_count_open = ShoppingItem.objects.filter(checked=False).count()
		shopping_items = list(ShoppingItem.objects.all().order_by("checked", "-created_at")[:10])

	if DashboardWidgetKind.TICKETS_STALE in widget_kinds:
		now = timezone.now()
		base_qs = (
			Ticket.objects.select_related("assignee", "template")
			.exclude(status=TicketStatus.DONE)
			.annotate(start_at=Coalesce("assigned_at", "created_at"))
		)
		for w in widgets:
			if w.kind != DashboardWidgetKind.TICKETS_STALE:
				continue
			min_days = int(getattr(w, "tickets_min_age_days", 7) or 7)
			limit = int(getattr(w, "tickets_limit", 10) or 10)
			min_days = max(0, min(3650, min_days))
			limit = max(1, min(100, limit))
			cutoff = now - timedelta(days=min_days)
			tickets = list(base_qs.filter(start_at__lte=cutoff).order_by("start_at")[:limit])
			for t in tickets:
				start = getattr(t, "start_at", None) or t.assigned_at or t.created_at
				if start:
					t.age_days = int((now - start).total_seconds() // 86400)
				else:
					t.age_days = None
			w.tickets = tickets

	return render(
		request,
		"tickets/dashboard.html",
		{
			"today": today,
			"widgets": widgets,
			"widget_kinds": widget_kinds,
			"cat_morning": cat_morning,
			"cat_evening": cat_evening,
			"dog_morning": dog_morning,
			"dog_evening": dog_evening,
			"toggle_groups": toggle_groups,
			"status_by_toggle_id": status_by_toggle_id,
			"shopping_items": shopping_items,
			"shopping_count_total": shopping_count_total,
			"shopping_count_open": shopping_count_open,
		},
	)


@login_required
def pets(request: HttpRequest) -> HttpResponse:
	return redirect("dashboard")


@login_required
def graphs(request: HttpRequest) -> HttpResponse:
	# Chris-only page.
	if (request.user.username or "") != "Chris":
		return redirect("dashboard")

	if request.method == "POST":
		measured_on_raw = (request.POST.get("measured_on") or "").strip()
		weight_raw = (request.POST.get("weight_kg") or "").strip().replace(",", ".")
		if measured_on_raw and weight_raw:
			try:
				measured_on = date.fromisoformat(measured_on_raw)
				float(weight_raw)
			except ValueError:
				pass
			else:
				WeightEntry.objects.create(
					created_by=request.user,
					measured_on=measured_on,
					weight_kg=weight_raw,
				)
		return redirect("graphs")

	entries = list(
		WeightEntry.objects.filter(created_by=request.user)
		.only("measured_on", "weight_kg")
		.order_by("measured_on", "created_at")
	)
	labels = [e.measured_on.isoformat() for e in entries]
	weights = [float(e.weight_kg) for e in entries]

	return render(
		request,
		"tickets/graphs.html",
		{
			"default_measured_on": timezone.localdate().isoformat(),
			"labels_json": json.dumps(labels),
			"weights_json": json.dumps(weights),
		},
	)


@login_required
def einkaufsliste(request: HttpRequest) -> HttpResponse:
	if request.method == "POST":
		if "clear" in request.POST:
			ShoppingItem.objects.all().delete()
			return redirect("einkaufsliste")

		if "toggle" in request.POST:
			item_id = request.POST.get("item_id")
			try:
				item_id_int = int(item_id)
			except (TypeError, ValueError):
				return redirect("einkaufsliste")
			item = ShoppingItem.objects.filter(id=item_id_int).first()
			if item:
				item.checked = not bool(item.checked)
				item.save(update_fields=["checked", "updated_at"])
			return redirect("einkaufsliste")

		text = (request.POST.get("text") or "").strip()
		if text:
			ShoppingItem.objects.create(text=text[:200], checked=False, created_by=request.user)
			return redirect("einkaufsliste")

	items = ShoppingItem.objects.all()
	return render(request, "tickets/einkaufsliste.html", {"items": items})


@login_required
def scoreboard(request: HttpRequest) -> HttpResponse:
	users = User.objects.all().order_by("username")
	users_list = list(users)

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
	for user in users_list:
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

	months_won = [{"username": u.username, "count": months_won_by_user_id.get(u.id, 0)} for u in users_list]

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
		total = sum(counts_by_user.get(u.id, 0) for u in users_list)
		max_count = max([counts_by_user.get(u.id, 0) for u in users_list] + [0])

		rows_for_tag = []
		for u in users_list:
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

	def _daily_graph(days: int):
		end_day = timezone.localdate()
		start_day = end_day - timedelta(days=max(1, days) - 1)
		labels = [(start_day + timedelta(days=i)).isoformat() for i in range((end_day - start_day).days + 1)]
		counts: dict[tuple[int, str], int] = {}
		for row in (
			Completion.objects.filter(completed_at__date__gte=start_day, completed_at__date__lte=end_day)
			.annotate(day=TruncDate("completed_at"))
			.values("day", "completed_by")
			.annotate(c=Count("id"))
		):
			day = row["day"]
			if not day:
				continue
			day_label = day.isoformat()
			counts[(int(row["completed_by"]), day_label)] = int(row["c"] or 0)

		series = []
		for u in users_list:
			series.append(
				{
					"label": u.username,
					"data": [counts.get((u.id, d), 0) for d in labels],
				}
			)
		return {"labels": labels, "series": series}

	def _monthly_graph_all_time():
		monthly_counts: dict[tuple[int, str], int] = {}
		months: list[str] = []
		seen: set[str] = set()
		for row in (
			Completion.objects.annotate(month=TruncMonth("completed_at"))
			.values("month", "completed_by")
			.annotate(c=Count("id"))
			.order_by("month")
		):
			month = row["month"]
			if not month:
				continue
			month_label = month.date().isoformat() if hasattr(month, "date") else month.isoformat()
			if month_label not in seen:
				seen.add(month_label)
				months.append(month_label)
			monthly_counts[(int(row["completed_by"]), month_label)] = int(row["c"] or 0)

		series = []
		for u in users_list:
			series.append(
				{
					"label": u.username,
					"data": [monthly_counts.get((u.id, m), 0) for m in months],
				}
			)
		return {"labels": months, "series": series}

	scoreboard_graph = {
		"week": _daily_graph(7),
		"month": _daily_graph(30),
		"all": _monthly_graph_all_time(),
	}

	return render(
		request,
		"tickets/scoreboard.html",
		{
			"rows": rows,
			"charts": charts,
			"month_history": month_history,
			"months_won": months_won,
			"tag_stats": tag_stats,
			"scoreboard_graph_json": json.dumps(scoreboard_graph),
		},
	)

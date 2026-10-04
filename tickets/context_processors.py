from datetime import timedelta

from django.db import OperationalError, ProgrammingError
from django.utils import timezone

from .access import can_view_graphs
from .models import UserActivity, UserAvailability


def graphs_access(request):
	return {"can_view_graphs": can_view_graphs(request.user)}


def user_presence(request):
	is_abwesend = False
	active_users = []
	if request.user.is_authenticated:
		try:
			is_abwesend = UserAvailability.objects.filter(user=request.user, is_absent=True).exists()
			active_since = timezone.now() - timedelta(minutes=2)
			active_users = list(
				UserActivity.objects.filter(last_seen__gte=active_since)
				.exclude(user=request.user)
				.order_by("user__username")
				.values_list("user__username", flat=True)
			)
		except (OperationalError, ProgrammingError):
			is_abwesend = False
			active_users = []
	return {"is_abwesend": is_abwesend, "active_users": active_users}
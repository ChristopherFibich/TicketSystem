from django.db import OperationalError, ProgrammingError

from .access import can_view_graphs
from .models import UserAvailability


def graphs_access(request):
	return {"can_view_graphs": can_view_graphs(request.user)}


def user_presence(request):
	is_abwesend = False
	if request.user.is_authenticated:
		try:
			is_abwesend = UserAvailability.objects.filter(user=request.user, is_absent=True).exists()
		except (OperationalError, ProgrammingError):
			is_abwesend = False
	return {"is_abwesend": is_abwesend}
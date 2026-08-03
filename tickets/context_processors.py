from .access import can_view_graphs
from .models import UserAvailability


def graphs_access(request):
	return {"can_view_graphs": can_view_graphs(request.user)}


def user_presence(request):
	is_abwesend = False
	if request.user.is_authenticated:
		is_abwesend = UserAvailability.objects.filter(user=request.user, is_absent=True).exists()
	return {"is_abwesend": is_abwesend}
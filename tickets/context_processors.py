from .access import can_view_graphs


def graphs_access(request):
	return {"can_view_graphs": can_view_graphs(request.user)}
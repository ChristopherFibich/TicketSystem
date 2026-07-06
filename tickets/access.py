from __future__ import annotations


def can_view_graphs(user) -> bool:
	if not user.is_authenticated:
		return False
	if user.is_superuser:
		return True
	return user.groups.filter(name__iexact="Graphs").exists()
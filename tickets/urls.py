from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("haushalt/", views.haushalt_tickets, name="haushalt_tickets"),
    path("haushalt/templates/new/", views.ticket_template_create, name="ticket_template_create"),
    path("templates/", views.ticket_templates, name="ticket_templates"),
    path("templates/<int:pk>/edit/", views.ticket_template_edit, name="ticket_template_edit"),
    path("daily/", views.haushalt_tickets, name="daily_tickets"),
    path("todo/", views.todo_tickets, name="todo_tickets"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("abwesend/", views.abwesend_toggle, name="abwesend_toggle"),
    path("activity/heartbeat/", views.activity_heartbeat, name="activity_heartbeat"),
    path("graphs/", views.graphs, name="graphs"),
    path("pets/", views.pets, name="pets"),
    path("einkaufsliste/", views.einkaufsliste, name="einkaufsliste"),
    path("all/", views.all_tickets, name="all_tickets"),
    path("help/", views.help_page, name="help_page"),
    path("tickets/new/", views.ticket_create, name="ticket_create"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("scoreboard/", views.scoreboard, name="scoreboard"),
]

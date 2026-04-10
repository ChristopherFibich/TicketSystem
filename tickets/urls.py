from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("my/", views.my_tickets, name="my_tickets"),
    path("all/", views.all_tickets, name="all_tickets"),
    path("help/", views.help_page, name="help_page"),
    path("tickets/new/", views.ticket_create, name="ticket_create"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("scoreboard/", views.scoreboard, name="scoreboard"),
]

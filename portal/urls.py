from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.start, name="start"),
    path("jahr/<int:jahr>/", views.start, name="jahr"),
    path("anmelden/", views.anmelden, name="anmelden"),
    path("anmelden/gesendet/", views.gesendet, name="gesendet"),
    path("anmelden/link/<str:token>/", views.token, name="token"),
    path("abmelden/", views.abmelden, name="abmelden"),
    path("datenschutz/", views.datenschutz, name="datenschutz"),
    path("anleitung/", views.anleitung, name="anleitung"),
]

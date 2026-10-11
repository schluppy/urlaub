from django.urls import path

from . import views

app_name = "kalender"

urlpatterns = [
    path("", views.start, name="start"),
    path("<int:jahr>/", views.jahr, name="jahr"),
    path("<int:jahr>/pdf/", views.pdf, name="pdf"),
]

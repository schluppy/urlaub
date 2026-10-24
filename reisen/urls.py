from django.urls import path

from . import views

app_name = "reisen"

urlpatterns = [
    path("<int:pk>/", views.reise, name="reise"),
    path("<int:pk>/route/", views.route, name="route"),
    path("<int:pk>/etappe/<int:etappe>/aufteilen/", views.aufteilen, name="aufteilen"),
    path("<int:pk>/excel/", views.excel, name="excel"),
    path("<int:pk>/pdf/", views.pdf, name="pdf"),
    path("<int:pk>/track/<int:track>.gpx", views.track_gpx, name="track_gpx"),
    path("kachel/tomtom/<int:z>/<int:x>/<int:y>.png", views.tomtom_kachel, name="kachel"),
]

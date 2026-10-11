from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Urlaubsplaner – Verwaltung"
admin.site.site_title = "Urlaubsplaner"
admin.site.index_title = "Daten bearbeiten"
admin.site.site_url = "/"

urlpatterns = [
    path("verwaltung/", admin.site.urls),
    path("kalender/", include("kalender.urls")),
    path("reise/", include("reisen.urls")),
    path("teilen/", include("freigaben.urls")),
    path("", include("portal.urls")),
]

from django.urls import path

from . import views

app_name = "freigaben"

urlpatterns = [
    path("reise/<int:pk>/", views.reise_teilen, name="reise"),
    path("kalender/<int:jahr>/", views.kalender_teilen, name="kalender"),
    path("<int:pk>/beenden/", views.beenden, name="beenden"),
    path("kalender-abo/", views.abo, name="abo"),
    path("abo/<str:token>.ics", views.abo_feed, name="abo_feed"),
    path("widget/", views.widget, name="widget"),
    path("widget/urlaubswidget.apk", views.widget_apk, name="widget_apk"),
    path("widget/<str:token>.json", views.widget_daten, name="widget_daten"),
    # öffentlich, ohne Anmeldung
    path("<str:token>/", views.ansehen, name="ansehen"),
    path("<str:token>/kalender.pdf", views.kalender_pdf, name="kalender_pdf"),
]

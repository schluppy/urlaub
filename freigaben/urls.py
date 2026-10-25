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
    path("widget/<str:token>/urlaubswidget.apk", views.widget_apk_link, name="widget_apk_link"),
    path("tracking/", views.tracking, name="tracking"),
    path("tracking/tracking.apk", views.tracking_apk, name="tracking_apk"),
    path("widget/<str:token>/etappen.json", views.tracking_daten, name="tracking_daten"),
    path("widget/<str:token>/tracking.apk", views.tracking_apk_link, name="tracking_apk_link"),
    path("widget/<str:token>/reisen.json", views.tracking_reisen, name="tracking_reisen"),
    path("widget/<str:token>/reise/<int:pk>/track", views.tracking_hochladen, name="tracking_hochladen"),
    # öffentlich, ohne Anmeldung
    path("<str:token>/", views.ansehen, name="ansehen"),
    path("<str:token>/kalender.pdf", views.kalender_pdf, name="kalender_pdf"),
]

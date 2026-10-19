package de.urlaubsplaner.widget

import android.app.AlarmManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId

/**
 * Das Widget rechnet die Tage selbst und zeichnet sich kurz nach Mitternacht (und zur Startzeit) neu.
 * Den Urlaubsplaner fragt es höchstens einmal am Tag; „Jetzt aktualisieren“ in der App jederzeit.
 */
class WidgetProvider : AppWidgetProvider() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            NEU_ZEICHNEN, Intent.ACTION_TIME_CHANGED, Intent.ACTION_TIMEZONE_CHANGED -> aktualisieren(context)
            else -> super.onReceive(context, intent)
        }
    }

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) = aktualisieren(context)

    override fun onDisabled(context: Context) {
        context.getSystemService(AlarmManager::class.java).cancel(wecker(context))
    }

    private fun aktualisieren(context: Context) {
        zeichnen(context)
        val speicher = Speicher(context)
        if (speicher.url == null || System.currentTimeMillis() - speicher.stand < EIN_TAG) return
        val ergebnis = goAsync()
        Thread {
            try {
                speicher.abrufen()
                zeichnen(context)
            } finally {
                ergebnis.finish()
            }
        }.start()
    }

    companion object {
        private const val NEU_ZEICHNEN = "de.urlaubsplaner.widget.NEU_ZEICHNEN"
        private const val EIN_TAG = 20L * 60 * 60 * 1000   // etwas kürzer, damit der tägliche Abruf nicht knapp verpasst wird

        /** Alle Widgets neu zeichnen und den nächsten Wecker stellen. */
        fun zeichnen(context: Context) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, WidgetProvider::class.java))
            if (ids.isEmpty()) return
            val speicher = Speicher(context)
            val anzeige = Anzeige.aus(speicher)
            val oeffnen = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val ansicht = RemoteViews(context.packageName, R.layout.widget).apply {
                setImageViewBitmap(R.id.kreis, anzeige.bild)
                setTextViewText(R.id.titel, anzeige.titel)
                setOnClickPendingIntent(R.id.widget, oeffnen)
            }
            manager.updateAppWidget(ids, ansicht)
            wecken(context, anzeige.reise)
        }

        private fun wecker(context: Context): PendingIntent =
            PendingIntent.getBroadcast(context, 0,
                Intent(context, WidgetProvider::class.java).setAction(NEU_ZEICHNEN),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)

        /** Kurz nach Mitternacht – oder zur Startzeit, wenn die Reise heute beginnt. */
        private fun wecken(context: Context, reise: Reise?) {
            val zone = ZoneId.systemDefault()
            var zeit = LocalDate.now().plusDays(1).atStartOfDay().plusMinutes(1)
            val start = reise?.uhrzeit?.let { reise.datum.atTime(it) }
            if (start != null && start.isAfter(LocalDateTime.now()) && start.isBefore(zeit)) zeit = start
            context.getSystemService(AlarmManager::class.java)
                .setAndAllowWhileIdle(AlarmManager.RTC, zeit.atZone(zone).toInstant().toEpochMilli(), wecker(context))
        }
    }
}

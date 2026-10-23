package de.urlaubsplaner.tracking

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent

/** Benachrichtigungen: die dauerhafte während der Aufzeichnung und „Fahrt prüfen“ danach. */
object Hinweise {
    private const val KANAL_AUFZEICHNUNG = "aufzeichnung"
    private const val KANAL_FAHRT = "fahrt"
    const val ID_AUFZEICHNUNG = 1
    private const val ID_FAHRT = 2

    fun kanaele(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(KANAL_AUFZEICHNUNG, "Aufzeichnung läuft", NotificationManager.IMPORTANCE_LOW))
        manager.createNotificationChannel(
            NotificationChannel(KANAL_FAHRT, "Fahrt beendet", NotificationManager.IMPORTANCE_DEFAULT))
    }

    fun aufzeichnung(context: Context, text: String): Notification {
        val beenden = PendingIntent.getService(context, 1,
            Intent(context, AufzeichnungsDienst::class.java).setAction(AufzeichnungsDienst.BEENDEN),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        return Notification.Builder(context, KANAL_AUFZEICHNUNG)
            .setSmallIcon(R.drawable.icon_klein)
            .setContentTitle("Fahrt wird aufgezeichnet")
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(oeffnen(context, MainActivity::class.java, null))
            .addAction(Notification.Action.Builder(null, "Fahrt beenden", beenden).build())
            .build()
    }

    fun aktualisieren(context: Context, text: String) =
        context.getSystemService(NotificationManager::class.java).notify(ID_AUFZEICHNUNG, aufzeichnung(context, text))

    fun fahrtBeendet(context: Context, fahrt: Long, text: String) {
        val hinweis = Notification.Builder(context, KANAL_FAHRT)
            .setSmallIcon(R.drawable.icon_klein)
            .setContentTitle("Fahrt beendet – prüfen und speichern")
            .setContentText(text)
            .setAutoCancel(true)
            .setContentIntent(oeffnen(context, FahrtActivity::class.java, fahrt))
            .build()
        context.getSystemService(NotificationManager::class.java).notify(ID_FAHRT, hinweis)
    }

    fun fehler(context: Context, text: String) {
        val hinweis = Notification.Builder(context, KANAL_FAHRT)
            .setSmallIcon(R.drawable.icon_klein)
            .setContentTitle("Tracking kann nicht aufzeichnen")
            .setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setContentIntent(oeffnen(context, MainActivity::class.java, null))
            .build()
        context.getSystemService(NotificationManager::class.java).notify(ID_FAHRT, hinweis)
    }

    private fun oeffnen(context: Context, ziel: Class<*>, fahrt: Long?): PendingIntent {
        val intent = Intent(context, ziel).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        if (fahrt != null) intent.putExtra(FahrtActivity.FAHRT, fahrt)
        return PendingIntent.getActivity(context, fahrt?.toInt() ?: 0, intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }
}

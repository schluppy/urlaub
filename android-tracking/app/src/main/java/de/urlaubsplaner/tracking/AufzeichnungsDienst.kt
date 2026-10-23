package de.urlaubsplaner.tracking

import android.Manifest
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.util.Log

/**
 * Zeichnet im Vordergrund jede Sekunde den GPS-Standort in das offene Teilstück auf.
 * Fällt das GPS aus (Tunnel), läuft das Teilstück weiter – eine Lücke ist keine Pause.
 */
class AufzeichnungsDienst : Service(), LocationListener {
    private var faden: HandlerThread? = null
    private var teil: Long? = null
    private var letzter: Punkt? = null
    private var meter = 0.0
    private var beginn = 0L
    private var angezeigt = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == BEENDEN) {
            Thread { Datenbank.von(this).offeneFahrt()?.let { Steuerung.beenden(this, it.id, null) } }.start()
            return START_NOT_STICKY
        }
        if (!erlaubt(this)) {
            stopSelf()
            return START_NOT_STICKY
        }
        startForeground(Hinweise.ID_AUFZEICHNUNG, Hinweise.aufzeichnung(this, "Warte auf GPS …"),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        if (faden == null) aufnehmen()
        return START_STICKY   // wird der Dienst beendet, startet Android ihn neu und er macht weiter
    }

    private fun aufnehmen() {
        val db = Datenbank.von(this)
        val fahrt = db.offeneFahrt()?.takeIf { it.zustand == Zustand.LAEUFT }
        if (fahrt == null) {
            stopSelf()
            return
        }
        teil = db.offenesTeil(fahrt.id) ?: db.neuesTeil(fahrt.id, System.currentTimeMillis())
        val bisher = db.teile(fahrt.id)
        meter = bisher.sumOf { it.meter }
        letzter = bisher.lastOrNull { it.id == teil }?.punkte?.lastOrNull()
        beginn = fahrt.beginn
        faden = HandlerThread("gps").also { it.start() }
        getSystemService(LocationManager::class.java)
            .requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 0f, this, faden!!.looper)
        Log.i("Tracking", "Aufzeichnung läuft: Fahrt ${fahrt.id}, Teil $teil")
    }

    override fun onLocationChanged(ort: Location) {
        if (ort.hasAccuracy() && ort.accuracy > Regeln.GENAUIGKEIT_M) return
        val p = Punkt(ort.time, ort.latitude, ort.longitude, if (ort.hasAltitude()) ort.altitude else null)
        Datenbank.von(this).punkt(teil ?: return, p)
        letzter?.let { meter += abstand(it.breite, it.laenge, p.breite, p.laenge) }
        letzter = p
        if (p.zeit - angezeigt > 30_000) {
            angezeigt = p.zeit
            val minuten = (p.zeit - beginn) / 60_000
            Hinweise.aktualisieren(this, String.format("%.1f km · %d:%02d h seit Beginn", meter / 1000, minuten / 60, minuten % 60))
        }
    }

    override fun onProviderDisabled(provider: String) {
        Hinweise.fehler(this, "Der Standort ist ausgeschaltet – die Fahrt wird nicht aufgezeichnet.")
    }

    override fun onDestroy() {
        getSystemService(LocationManager::class.java).removeUpdates(this)
        faden?.quitSafely()
        faden = null
        super.onDestroy()
    }

    companion object {
        const val BEENDEN = "de.urlaubsplaner.tracking.BEENDEN"

        /** Ohne Standort „immer“ darf ein Dienst, der aus dem Hintergrund startet, kein GPS nutzen. */
        fun erlaubt(context: Context) =
            context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED &&
                context.checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION) == PackageManager.PERMISSION_GRANTED

        fun starten(context: Context) {
            if (!erlaubt(context)) {
                Hinweise.fehler(context, "Die App darf den Standort nicht „immer“ nutzen. Bitte in der App die Berechtigungen erteilen.")
                return
            }
            context.startForegroundService(Intent(context, AufzeichnungsDienst::class.java))
        }

        fun anhalten(context: Context) {
            context.stopService(Intent(context, AufzeichnungsDienst::class.java))
        }
    }
}

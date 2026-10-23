package de.urlaubsplaner.tracking

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.util.Log
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * Entscheidet, was beim Verbinden und Trennen des Autos passiert:
 *
 * - verbunden an einem Etappentag → neue Fahrt; während einer Pause → neues Teilstück
 * - getrennt nahe einem Etappenziel → Fahrt beendet, Hinweis „prüfen und speichern“
 * - getrennt woanders → Pause; nach [Regeln.PAUSE_HOECHSTENS] gilt die Fahrt als beendet
 */
object Steuerung {
    private const val TAG = "Tracking"
    const val PAUSE_VORBEI = "de.urlaubsplaner.tracking.PAUSE_VORBEI"

    /** Das Auto ist verbunden – oder „Jetzt starten“ (`vonHand`, ohne Prüfung des Tages). */
    fun verbunden(context: Context, vonHand: Boolean = false) {
        val db = Datenbank.von(context)
        val jetzt = System.currentTimeMillis()
        var fahrt = db.offeneFahrt()
        if (fahrt?.zustand == Zustand.PAUSE) {
            val seit = db.pauseSeit(fahrt.id) ?: fahrt.beginn
            if (jetzt - seit > Regeln.PAUSE_HOECHSTENS.toMillis()) {
                beenden(context, fahrt.id, null)
                fahrt = null
            } else {
                Log.i(TAG, "Weiter nach Pause: Fahrt ${fahrt.id}")
                pauseweckerAus(context)
                db.setzen(fahrt.id, Zustand.LAEUFT)
                db.neuesTeil(fahrt.id, jetzt)
                AufzeichnungsDienst.starten(context)
                return
            }
        }
        if (fahrt?.zustand == Zustand.LAEUFT) {
            AufzeichnungsDienst.starten(context)   // läuft schon; nach einem Neustart des Handys wieder aufnehmen
            return
        }
        val speicher = Speicher(context)
        if (!vonHand && !(speicher.automatik && Regeln.etappentag(LocalDate.now(), speicher.etappen()))) {
            Log.i(TAG, "Auto verbunden, aber heute ist kein Etappentag")
            return
        }
        val neu = db.neueFahrt(jetzt)
        db.neuesTeil(neu, jetzt)
        Log.i(TAG, "Neue Fahrt $neu")
        AufzeichnungsDienst.starten(context)
    }

    /** Das Auto ist getrennt: am Ziel beenden, sonst Pause. */
    fun getrennt(context: Context) {
        val db = Datenbank.von(context)
        val fahrt = db.offeneFahrt()?.takeIf { it.zustand == Zustand.LAEUFT } ?: return
        val jetzt = System.currentTimeMillis()
        db.teilBeenden(fahrt.id, jetzt)
        AufzeichnungsDienst.anhalten(context)
        val ziel = db.letzterPunkt(fahrt.id)?.let { p ->
            Regeln.zielInDerNaehe(p.breite, p.laenge, tag(fahrt.beginn), LocalDate.now(), Speicher(context).etappen())
        }
        if (ziel != null) {
            beenden(context, fahrt.id, ziel.name)
        } else {
            Log.i(TAG, "Pause: Fahrt ${fahrt.id}")
            db.setzen(fahrt.id, Zustand.PAUSE)
            pauseweckerAn(context, jetzt + Regeln.PAUSE_HOECHSTENS.toMillis())
        }
    }

    /** Fahrt abschließen (am Ziel, von Hand oder nach zu langer Pause) und zum Prüfen anbieten. */
    fun beenden(context: Context, fahrtId: Long, ziel: String?) {
        val db = Datenbank.von(context)
        val jetzt = System.currentTimeMillis()
        db.teilBeenden(fahrtId, jetzt)
        AufzeichnungsDienst.anhalten(context)
        pauseweckerAus(context)
        val teile = db.teile(fahrtId)
        if (teile.all { it.punkte.isEmpty() }) {
            Log.i(TAG, "Fahrt $fahrtId ohne Standorte – verworfen")
            db.loeschen(fahrtId)
            return
        }
        db.setzen(fahrtId, Zustand.FERTIG, ende = teile.mapNotNull { it.ende }.maxOrNull() ?: jetzt, ziel = ziel)
        val km = teile.sumOf { it.meter } / 1000
        val text = (if (ziel != null) "Angekommen: $ziel · " else "") +
            String.format("%.0f km in %d Teilstück%s", km, teile.size, if (teile.size == 1) "" else "en")
        Hinweise.fahrtBeendet(context, fahrtId, text)
    }

    /** Der Wecker nach einer langen Pause. */
    fun pauseVorbei(context: Context) {
        val db = Datenbank.von(context)
        val fahrt = db.offeneFahrt()?.takeIf { it.zustand == Zustand.PAUSE } ?: return
        val seit = db.pauseSeit(fahrt.id) ?: fahrt.beginn
        if (System.currentTimeMillis() - seit >= Regeln.PAUSE_HOECHSTENS.toMillis() - 60_000) beenden(context, fahrt.id, null)
    }

    private fun tag(millis: Long): LocalDate = Instant.ofEpochMilli(millis).atZone(ZoneId.systemDefault()).toLocalDate()

    private fun wecker(context: Context) = PendingIntent.getBroadcast(context, 0,
        Intent(context, AutoEmpfaenger::class.java).setAction(PAUSE_VORBEI),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    // ungefährer Wecker – braucht keine Berechtigung für exakte Alarme
    private fun pauseweckerAn(context: Context, wann: Long) =
        context.getSystemService(AlarmManager::class.java).setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, wann, wecker(context))

    private fun pauseweckerAus(context: Context) = context.getSystemService(AlarmManager::class.java).cancel(wecker(context))
}

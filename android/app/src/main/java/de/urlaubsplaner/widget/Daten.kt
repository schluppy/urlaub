package de.urlaubsplaner.widget

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.temporal.ChronoUnit

/** Eine Reise aus dem Urlaubsplaner; `uhrzeit` ist der Start der ersten Etappe, falls geplant. */
data class Reise(
    val titel: String,
    val datum: LocalDate,
    val uhrzeit: LocalTime?,
    val wartenSeit: LocalDate,
    val link: String,
) {
    /** Die Reise zählt als begonnen ab der Startzeit, ohne Startzeit erst am Tag danach. */
    fun begonnen(jetzt: LocalDateTime): Boolean =
        if (uhrzeit != null) !jetzt.isBefore(datum.atTime(uhrzeit)) else jetzt.toLocalDate().isAfter(datum)

    fun tage(heute: LocalDate): Long = ChronoUnit.DAYS.between(heute, datum)

    /** Wie viel der Wartezeit seit der letzten Rückkehr vorbei ist (0 … 1) – für den Ring. */
    fun anteil(heute: LocalDate): Float {
        val gesamt = ChronoUnit.DAYS.between(wartenSeit, datum).coerceAtLeast(1)
        val vorbei = ChronoUnit.DAYS.between(wartenSeit, heute)
        return (vorbei.toFloat() / gesamt).coerceIn(0f, 1f)
    }
}

/** Gespeicherter Stand: Link, letzte Antwort des Servers, Zeitpunkt und ggf. Fehler. */
class Speicher(context: Context) {
    private val prefs = context.getSharedPreferences("urlaub", Context.MODE_PRIVATE)

    var url: String?
        get() = prefs.getString("url", null)
        set(wert) = prefs.edit().putString("url", wert).remove("json").remove("stand").remove("fehler").apply()

    val stand: Long get() = prefs.getLong("stand", 0)

    /** Wann der Hintergrund-Abruf bzw. der Wecker des Widgets zuletzt lief – zur Fehlersuche in der App. */
    var letzterJob: Long
        get() = prefs.getLong("letzter_job", 0)
        set(wert) = prefs.edit().putLong("letzter_job", wert).apply()
    var planFehler: String?
        get() = prefs.getString("plan_fehler", null)
        set(wert) = prefs.edit().putString("plan_fehler", wert).apply()
    var letzterWecker: Long
        get() = prefs.getLong("letzter_wecker", 0)
        set(wert) = prefs.edit().putLong("letzter_wecker", wert).apply()
    val fehler: String? get() = prefs.getString("fehler", null)

    fun reisen(): List<Reise> {
        val json = prefs.getString("json", null) ?: return emptyList()
        return try { lesen(json) } catch (e: Exception) { emptyList() }
    }

    /** Die nächste Reise, die noch nicht begonnen hat. */
    fun naechste(jetzt: LocalDateTime = LocalDateTime.now()): Reise? = reisen().firstOrNull { !it.begonnen(jetzt) }

    /** Fragt den Urlaubsplaner. Läuft nicht im UI-Thread. Gibt bei Erfolg true zurück. */
    fun abrufen(): Boolean {
        val adresse = url ?: return false
        val fehlertext = try {
            val verbindung = URL(adresse).openConnection() as HttpURLConnection
            verbindung.connectTimeout = 15000
            verbindung.readTimeout = 15000
            verbindung.setRequestProperty("Accept", "application/json")
            try {
                when (verbindung.responseCode) {
                    200 -> {
                        val json = verbindung.inputStream.bufferedReader().use { it.readText() }
                        lesen(json)   // prüft, ob die Antwort passt
                        prefs.edit().putString("json", json).putLong("stand", System.currentTimeMillis())
                            .remove("fehler").apply()
                        return true
                    }
                    404 -> "Der Link gilt nicht (mehr). Bitte im Urlaubsplaner neu einrichten."
                    else -> "Der Urlaubsplaner antwortet mit Fehler ${verbindung.responseCode}."
                }
            } finally {
                verbindung.disconnect()
            }
        } catch (e: Exception) {
            "Keine Verbindung zum Urlaubsplaner."
        }
        prefs.edit().putString("fehler", fehlertext).apply()
        return false
    }

    private fun lesen(json: String): List<Reise> {
        val liste = JSONObject(json).getJSONArray("reisen")
        return (0 until liste.length()).map { i ->
            val r = liste.getJSONObject(i)
            Reise(
                titel = r.getString("titel"),
                datum = LocalDate.parse(r.getString("datum")),
                uhrzeit = if (r.isNull("uhrzeit")) null else LocalTime.parse(r.getString("uhrzeit")),
                wartenSeit = LocalDate.parse(r.getString("warten_seit")),
                link = r.optString("link"),
            )
        }
    }
}

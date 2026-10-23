package de.urlaubsplaner.tracking

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.time.LocalTime

/** Einstellungen und die zuletzt geholten Etappen. */
class Speicher(context: Context) {
    private val prefs = context.getSharedPreferences("tracking", Context.MODE_PRIVATE)

    var url: String?
        get() = prefs.getString("url", null)
        set(wert) = prefs.edit().putString("url", wert).remove("json").remove("stand").remove("fehler").apply()

    /** Bluetooth-Adresse und Name des Autos. */
    var autoAdresse: String?
        get() = prefs.getString("auto_adresse", null)
        set(wert) = prefs.edit().putString("auto_adresse", wert).apply()
    var autoName: String?
        get() = prefs.getString("auto_name", null)
        set(wert) = prefs.edit().putString("auto_name", wert).apply()

    /** Automatik aus: dann reagiert die App nicht auf das Auto. */
    var automatik: Boolean
        get() = prefs.getBoolean("automatik", true)
        set(wert) = prefs.edit().putBoolean("automatik", wert).apply()

    val stand: Long get() = prefs.getLong("stand", 0)
    val fehler: String? get() = prefs.getString("fehler", null)

    fun etappen(): List<Etappe> {
        val json = prefs.getString("json", null) ?: return emptyList()
        return try { lesen(json) } catch (e: Exception) { emptyList() }
    }

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

    private fun lesen(json: String): List<Etappe> {
        val liste = JSONObject(json).getJSONArray("etappen")
        return (0 until liste.length()).map { i ->
            val e = liste.getJSONObject(i)
            Etappe(
                reise = e.getString("reise"),
                datum = LocalDate.parse(e.getString("datum")),
                startzeit = if (e.isNull("startzeit")) null else LocalTime.parse(e.getString("startzeit")),
                von = ort(e.getJSONObject("von")),
                nach = ort(e.getJSONObject("nach")),
            )
        }
    }

    private fun ort(o: JSONObject) = Ort(
        name = o.getString("name"),
        typ = o.optString("typ"),
        breite = if (o.isNull("breite")) null else o.getDouble("breite"),
        laenge = if (o.isNull("laenge")) null else o.getDouble("laenge"),
    )
}

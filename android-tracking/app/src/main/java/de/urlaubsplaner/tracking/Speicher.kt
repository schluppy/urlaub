package de.urlaubsplaner.tracking

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.zip.GZIPOutputStream
import java.time.LocalDate
import java.time.LocalTime

/** Eine Reise zur Auswahl beim Hochladen eines Tracks. */
data class Reise(val id: Long, val titel: String, val von: LocalDate, val bis: LocalDate)

/** Neuere Version der App auf dem Server: Anzeigename und Link zum Herunterladen. */
data class Update(val version: String, val download: String)

/** Einstellungen und die zuletzt geholten Etappen. */
class Speicher(private val context: Context) {
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

    /** An welchem Tag zuletzt auf fehlende Rechte hingewiesen wurde (JJJJ-MM-TT) – höchstens einmal am Tag. */
    var rechteGemeldet: String?
        get() = prefs.getString("rechte_gemeldet", null)
        set(wert) = prefs.edit().putString("rechte_gemeldet", wert).apply()

    /** Die Version dieser App, z. B. „0.3“. */
    val version: String get() = paket().versionName ?: ""

    /** Meldet der Urlaubsplaner eine neuere App als die installierte? */
    fun update(): Update? = try {
        val app = JSONObject(prefs.getString("json", null) ?: "{}").optJSONObject("app")
        if (app != null && app.optLong("code") > paket().longVersionCode && app.optString("download").isNotEmpty()) {
            Update(app.optString("name"), app.getString("download"))
        } else null
    } catch (e: Exception) {
        null
    }

    private fun paket() = context.packageManager.getPackageInfo(context.packageName, 0)

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

    /** Adresse neben etappen.json – derselbe geheime Link, z. B. „reisen.json“. */
    private fun adresse(pfad: String): String {
        val basis = url ?: throw HochladenFehler("Die App ist noch nicht eingerichtet.")
        return basis.substringBeforeLast("/") + "/" + pfad
    }

    /** Die zeitlich nächsten Reisen zum Datum der Fahrt, die nächste zuerst. Nicht im UI-Thread. */
    fun reisen(datum: LocalDate): List<Reise> {
        val json = anfrage(adresse("reisen.json?datum=" + URLEncoder.encode(datum.toString(), "UTF-8")), null)
        val liste = JSONObject(json).getJSONArray("reisen")
        return (0 until liste.length()).map { i ->
            val r = liste.getJSONObject(i)
            Reise(r.getLong("id"), r.getString("titel"), LocalDate.parse(r.getString("von")), LocalDate.parse(r.getString("bis")))
        }
    }

    /** GPX gzip-komprimiert zur Reise hochladen. Gibt die Antwort des Urlaubsplaners zurück. Nicht im UI-Thread. */
    fun hochladen(reise: Long, gpx: String): JSONObject =
        JSONObject(anfrage(adresse("reise/$reise/track"), gpx.toByteArray()))

    private fun anfrage(adresse: String, gpx: ByteArray?): String {
        val verbindung = try { URL(adresse).openConnection() as HttpURLConnection }
        catch (e: Exception) { throw HochladenFehler("Keine Verbindung zum Urlaubsplaner.") }
        try {
            verbindung.connectTimeout = 15000
            verbindung.readTimeout = 60000
            verbindung.setRequestProperty("Accept", "application/json")
            if (gpx != null) {
                verbindung.requestMethod = "POST"
                verbindung.doOutput = true
                verbindung.setRequestProperty("Content-Type", "application/gzip")
                GZIPOutputStream(verbindung.outputStream).use { it.write(gpx) }
            }
            val code = verbindung.responseCode
            val text = (if (code < 400) verbindung.inputStream else verbindung.errorStream)
                ?.bufferedReader()?.use { it.readText() } ?: ""
            return when (code) {
                200, 201 -> text
                400 -> throw HochladenFehler(try { JSONObject(text).getString("fehler") } catch (e: Exception) { "Die Datei wurde abgelehnt." })
                404 -> throw HochladenFehler("Der Link oder die Reise gilt nicht (mehr).")
                else -> throw HochladenFehler("Der Urlaubsplaner antwortet mit Fehler $code.")
            }
        } catch (e: HochladenFehler) {
            throw e
        } catch (e: Exception) {
            throw HochladenFehler("Keine Verbindung zum Urlaubsplaner.")
        } finally {
            verbindung.disconnect()
        }
    }
}

/** Fehler beim Hochladen mit verständlicher Meldung. */
class HochladenFehler(meldung: String) : Exception(meldung)

package de.urlaubsplaner.tracking

import android.app.Activity
import android.app.AlertDialog
import android.content.ContentValues
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.view.Gravity
import android.widget.Button
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Eine Fahrt prüfen: Teilstücke behalten oder verwerfen, Pausen überbrücken („verbinden“)
 * und als GPX in „Download/Tracking“ speichern. Jede zusammenhängende Gruppe wird eine Datei.
 */
class FahrtActivity : Activity() {
    private var fahrtId = 0L
    private var teile: List<Teil> = emptyList()
    private val behalten = mutableListOf<CheckBox>()
    private val verbinden = mutableListOf<CheckBox>()
    private lateinit var inhalt: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        fahrtId = intent.getLongExtra(FAHRT, 0)
        inhalt = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(20), dp(20), dp(20)) }
        setContentView(ScrollView(this).apply { fitsSystemWindows = true; addView(inhalt) })
        laden()
    }

    private fun laden() {
        inhalt.removeAllViews()
        inhalt.addView(TextView(this).apply { text = "Lade …" })
        Thread {
            val db = Datenbank.von(this)
            val fahrt = db.fahrt(fahrtId)
            val geladen = if (fahrt != null) db.teile(fahrtId) else emptyList()
            runOnUiThread { if (fahrt == null) finish() else anzeigen(fahrt, geladen) }
        }.start()
    }

    private fun anzeigen(fahrt: Fahrt, geladen: List<Teil>) {
        teile = geladen
        behalten.clear()
        verbinden.clear()
        inhalt.removeAllViews()
        inhalt.addView(TextView(this).apply {
            text = "Fahrt ${MainActivity.zeit(fahrt.beginn)}"
            textSize = 22f
        })
        val km = teile.sumOf { it.meter } / 1000
        inhalt.addView(TextView(this).apply {
            text = (fahrt.ziel?.let { "Angekommen: $it\n" } ?: "") +
                String.format("%.1f km · %d Teilstück%s · %s", km, teile.size, if (teile.size == 1) "" else "e",
                    MainActivity.zustandText(fahrt.zustand))
            setPadding(0, dp(6), 0, dp(12))
        })

        if (fahrt.zustand == Zustand.LAEUFT || fahrt.zustand == Zustand.PAUSE) {
            inhalt.addView(Button(this).apply {
                text = "Fahrt jetzt beenden"
                setOnClickListener { Thread { Steuerung.beenden(this@FahrtActivity, fahrtId, null); runOnUiThread { laden() } }.start() }
            })
            return
        }

        val vorschlag = Regeln.verbindenVorschlag(teile)
        teile.forEachIndexed { i, teil ->
            if (i > 0) {
                val pause = Duration.ofMillis(teil.beginn - (teile[i - 1].ende ?: teile[i - 1].beginn))
                verbinden += CheckBox(this).apply {
                    text = "↕ Pause ${dauer(pause)} – mit dem vorigen verbinden"
                    isChecked = vorschlag[i - 1]
                    setPadding(dp(24), 0, 0, 0)
                    alpha = 0.8f
                }.also { inhalt.addView(it) }
            }
            behalten += CheckBox(this).apply {
                val bis = teil.ende ?: teil.punkte.lastOrNull()?.zeit ?: teil.beginn
                text = "${uhr(teil.beginn)}–${uhr(bis)} · " +
                    if (teil.punkte.isEmpty()) "keine Standorte"
                    else String.format("%.1f km · %s", teil.meter / 1000, dauer(Duration.ofMillis(bis - teil.beginn)))
                textSize = 17f
                isChecked = teil.punkte.size >= 2
                isEnabled = teil.punkte.isNotEmpty()
                minHeight = dp(48)
            }.also { inhalt.addView(it) }
        }

        inhalt.addView(Button(this).apply {
            text = if (fahrt.zustand == Zustand.GESPEICHERT) "Noch einmal als GPX speichern" else "Als GPX speichern"
            setOnClickListener { speichern(fahrt) }
        })
        inhalt.addView(Button(this).apply {
            text = "Fahrt löschen"
            setOnClickListener {
                AlertDialog.Builder(this@FahrtActivity)
                    .setMessage("Die Fahrt mit allen Standorten löschen? Gespeicherte GPX-Dateien bleiben erhalten.")
                    .setPositiveButton("Löschen") { _, _ -> Datenbank.von(this@FahrtActivity).loeschen(fahrtId); finish() }
                    .setNegativeButton("Abbrechen", null)
                    .show()
            }
        })
        inhalt.addView(TextView(this).apply {
            text = "Verbundene Teilstücke landen in einer GPX-Datei (je Teilstück ein Segment), getrennte in eigenen Dateien."
            alpha = 0.7f
            textSize = 13f
            gravity = Gravity.START
            setPadding(0, dp(12), 0, 0)
        })
    }

    private fun speichern(fahrt: Fahrt) {
        val gruppen = Regeln.gruppieren(teile, verbinden.map { it.isChecked }, behalten.map { it.isChecked })
        if (gruppen.isEmpty()) {
            Toast.makeText(this, "Kein Teilstück ausgewählt.", Toast.LENGTH_LONG).show()
            return
        }
        val dateien = gruppen.map { gruppe ->
            val titel = "Fahrt ${MainActivity.zeit(gruppe.first().beginn)}" + (fahrt.ziel?.takeIf { gruppe === gruppen.last() }?.let { " → $it" } ?: "")
            val werte = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, Gpx.name(gruppe))
                put(MediaStore.Downloads.MIME_TYPE, "application/gpx+xml")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Tracking")
            }
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, werte)!!
            contentResolver.openOutputStream(uri)!!.bufferedWriter().use { it.write(Gpx.schreiben(titel, gruppe)) }
            uri
        }
        Datenbank.von(this).setzen(fahrtId, Zustand.GESPEICHERT)
        AlertDialog.Builder(this)
            .setMessage("${dateien.size} GPX-Datei${if (dateien.size == 1) "" else "en"} in „Download/Tracking“ gespeichert.")
            .setPositiveButton("Teilen") { _, _ -> teilen(dateien) }
            .setNegativeButton("Fertig") { _, _ -> laden() }
            .show()
    }

    private fun teilen(dateien: List<Uri>) {
        val intent = if (dateien.size == 1) Intent(Intent.ACTION_SEND).putExtra(Intent.EXTRA_STREAM, dateien[0])
        else Intent(Intent.ACTION_SEND_MULTIPLE).putParcelableArrayListExtra(Intent.EXTRA_STREAM, ArrayList(dateien))
        intent.type = "application/gpx+xml"
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        startActivity(Intent.createChooser(intent, "GPX teilen"))
        laden()
    }

    private fun dp(wert: Int) = (wert * resources.displayMetrics.density).toInt()

    private fun uhr(millis: Long) = uhrzeit.format(Instant.ofEpochMilli(millis).atZone(ZoneId.systemDefault()))

    private fun dauer(d: Duration) = if (d.toHours() > 0) "${d.toHours()}:%02d h".format(d.toMinutesPart()) else "${d.toMinutes()} min"

    companion object {
        const val FAHRT = "fahrt"
        private val uhrzeit = DateTimeFormatter.ofPattern("HH:mm")
    }
}

package de.urlaubsplaner.widget

import android.app.Activity
import android.app.ActivityManager
import android.app.usage.UsageStatsManager
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import java.text.DateFormat
import java.util.Date

/** Einrichten, Stand ansehen und von Hand aktualisieren. */
class MainActivity : Activity() {
    private lateinit var speicher: Speicher
    private var detailsOffen = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.main)
        speicher = Speicher(this)

        findViewById<Button>(R.id.aktualisieren).setOnClickListener { abrufen() }
        findViewById<Button>(R.id.update_laden).setOnClickListener {
            speicher.update()?.let { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(it.download))) }
        }
        findViewById<Button>(R.id.details_knopf).setOnClickListener {
            detailsOffen = !detailsOffen
            detailsZeigen()
        }
        findViewById<Button>(R.id.oeffnen).setOnClickListener {
            speicher.naechste()?.link?.takeIf { it.isNotEmpty() }?.let {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(it)))
            }
        }
        findViewById<Button>(R.id.hinzufuegen).setOnClickListener {
            val manager = getSystemService(AppWidgetManager::class.java)
            if (manager.isRequestPinAppWidgetSupported) {
                manager.requestPinAppWidget(ComponentName(this, WidgetProvider::class.java), null, null)
            } else {
                Toast.makeText(this, "Lange auf den Startbildschirm drücken → Widgets → Urlaub", Toast.LENGTH_LONG).show()
            }
        }
        findViewById<Button>(R.id.speichern).setOnClickListener {
            einrichten(findViewById<EditText>(R.id.url).text.toString().trim())
        }
        findViewById<EditText>(R.id.url).setText(speicher.url ?: "")
        uebernehmen(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        uebernehmen(intent)
    }

    override fun onResume() {
        super.onResume()
        if (speicher.url != null) AbrufDienst.planen(this)
        anzeigen()
    }

    /** Link aus dem Knopf „Widget einrichten“ (urlaubswidget://einrichten?url=…). */
    private fun uebernehmen(intent: Intent?) {
        val daten = intent?.data ?: return
        if (daten.scheme == "urlaubswidget") {
            daten.getQueryParameter("url")?.let { einrichten(it) }
            setIntent(Intent(this, MainActivity::class.java))
        }
    }

    private fun einrichten(url: String) {
        if (!url.startsWith("https://") && !url.startsWith("http://")) {
            Toast.makeText(this, "Das ist kein gültiger Link.", Toast.LENGTH_LONG).show()
            return
        }
        speicher.url = url
        findViewById<EditText>(R.id.url).setText(url)
        AbrufDienst.planen(this)
        abrufen()
    }

    private fun abrufen() {
        if (speicher.url == null) {
            Toast.makeText(this, "Zuerst den Widget-Link eintragen.", Toast.LENGTH_LONG).show()
            return
        }
        findViewById<TextView>(R.id.status).text = "Frage den Urlaubsplaner …"
        Thread {
            speicher.abrufen()
            WidgetProvider.zeichnen(this)
            runOnUiThread { anzeigen() }
        }.start()
    }

    /** Wann Tage und Reisedaten zuletzt von selbst aktualisiert wurden und was Android im Hintergrund zulässt. */
    private fun details(): String {
        fun wann(zeit: Long) = if (zeit == 0L) "noch nie"
            else DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(zeit))
        val gruppe = when (getSystemService(UsageStatsManager::class.java).appStandbyBucket) {
            UsageStatsManager.STANDBY_BUCKET_ACTIVE -> "aktiv"
            UsageStatsManager.STANDBY_BUCKET_WORKING_SET -> "regelmäßig"
            UsageStatsManager.STANDBY_BUCKET_FREQUENT -> "häufig"
            UsageStatsManager.STANDBY_BUCKET_RARE -> "selten"
            UsageStatsManager.STANDBY_BUCKET_RESTRICTED -> "eingeschränkt"
            else -> "unbekannt"
        }
        return listOf(
            "Tage zuletzt aktualisiert: " + wann(speicher.letzterWecker),
            "Reisedaten zuletzt aktualisiert: " + wann(speicher.letzterJob),
            "Automatische Aktualisierung: " + (if (AbrufDienst.geplant(this)) "geplant" else "NICHT geplant"),
            "Android-Gruppe: $gruppe",
            "App-Version: ${speicher.version}",
        ).joinToString("\n")
    }

    /** Hinweise, die auch bei eingeklappten Details sichtbar bleiben. */
    private fun warnungen(): List<String> {
        val zeilen = mutableListOf<String>()
        speicher.planFehler?.let { zeilen += "⚠ Einplanen fehlgeschlagen: $it" }
        if (getSystemService(ActivityManager::class.java).isBackgroundRestricted) {
            zeilen += "⚠ Die Akkunutzung der App ist „Eingeschränkt“. Bitte unter App-Info → Akkunutzung " +
                "auf „Optimiert“ stellen, sonst aktualisiert sich das Widget nicht von selbst."
        }
        return zeilen
    }

    private fun anzeigen() {
        val anzeige = Anzeige.aus(speicher)
        findViewById<ImageView>(R.id.kreis).setImageBitmap(anzeige.bild)
        val zeilen = mutableListOf<String>()
        when {
            speicher.url == null -> zeilen += "Noch nicht eingerichtet. Im Urlaubsplaner unter Kalender → Handy-Widget " +
                "auf „Widget einrichten“ tippen."
            anzeige.reise != null -> zeilen += Anzeige.beschreibung(anzeige.reise)
            speicher.stand != 0L -> zeilen += "Keine geplante Reise."
        }
        speicher.fehler?.let { zeilen += "\n⚠ $it" }
        if (speicher.stand != 0L) {
            zeilen += "\nStand: " + DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date(speicher.stand))
        }
        if (speicher.url != null) warnungen().takeIf { it.isNotEmpty() }?.let { zeilen += "\n" + it.joinToString("\n") }
        findViewById<TextView>(R.id.status).text = zeilen.joinToString("\n")
        findViewById<Button>(R.id.oeffnen).isEnabled = anzeige.reise?.link?.isNotEmpty() == true
        val update = speicher.update()
        findViewById<View>(R.id.update).visibility = if (update != null) View.VISIBLE else View.GONE
        if (update != null) {
            findViewById<TextView>(R.id.update_text).text =
                "Neue Version ${update.version} verfügbar (installiert: ${speicher.version})"
        }
        findViewById<Button>(R.id.details_knopf).visibility = if (speicher.url != null) View.VISIBLE else View.GONE
        detailsZeigen()
    }

    private fun detailsZeigen() {
        val offen = detailsOffen && speicher.url != null
        findViewById<Button>(R.id.details_knopf).text = if (offen) "Details ausblenden" else "Details anzeigen"
        findViewById<TextView>(R.id.details).apply {
            visibility = if (offen) View.VISIBLE else View.GONE
            if (offen) text = details()
        }
    }
}

package de.urlaubsplaner.widget

import android.app.Activity
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Bundle
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.main)
        speicher = Speicher(this)

        findViewById<Button>(R.id.aktualisieren).setOnClickListener { abrufen() }
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
        findViewById<TextView>(R.id.status).text = zeilen.joinToString("\n")
        findViewById<Button>(R.id.oeffnen).isEnabled = anzeige.reise?.link?.isNotEmpty() == true
    }
}

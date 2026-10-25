package de.urlaubsplaner.tracking

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.bluetooth.BluetoothManager
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import java.text.DateFormat
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Date
import java.util.Locale

/** Einrichten, Stand ansehen, von Hand starten und beenden, Fahrten öffnen. */
class MainActivity : Activity() {
    private lateinit var speicher: Speicher
    private var detailsOffen = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.main)
        speicher = Speicher(this)
        Hinweise.kanaele(this)

        findViewById<Button>(R.id.starten).setOnClickListener { imHintergrund { Steuerung.verbunden(this, vonHand = true) } }
        findViewById<Button>(R.id.beenden).setOnClickListener {
            imHintergrund { Datenbank.von(this).offeneFahrt()?.let { Steuerung.beenden(this, it.id, null) } }
        }
        findViewById<Button>(R.id.update_laden).setOnClickListener {
            speicher.update()?.let { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(it.download))) }
        }
        findViewById<Button>(R.id.details_knopf).setOnClickListener {
            detailsOffen = !detailsOffen
            anzeigen()
        }
        findViewById<Switch>(R.id.automatik).setOnCheckedChangeListener { _, an -> speicher.automatik = an }
        findViewById<Button>(R.id.berechtigungen).setOnClickListener { berechtigungen() }
        findViewById<Button>(R.id.auto).setOnClickListener { autoWaehlen() }
        findViewById<Button>(R.id.aktualisieren).setOnClickListener { abrufen() }
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

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        anzeigen()
    }

    /** Link aus dem Knopf „Tracking einrichten“ (urlaubstracking://einrichten?url=…). */
    private fun uebernehmen(intent: Intent?) {
        val daten = intent?.data ?: return
        if (daten.scheme == "urlaubstracking") {
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
            Toast.makeText(this, "Zuerst den Etappen-Link eintragen.", Toast.LENGTH_LONG).show()
            return
        }
        Toast.makeText(this, "Frage den Urlaubsplaner …", Toast.LENGTH_SHORT).show()
        imHintergrund { speicher.abrufen() }
    }

    private fun imHintergrund(arbeit: () -> Unit) {
        Thread {
            arbeit()
            runOnUiThread { anzeigen() }
        }.start()
    }

    // --- Berechtigungen: der Reihe nach, denn „Standort immer“ fragt Android erst nach „beim Verwenden“ ---

    private fun hat(recht: String) = Rechte.hat(this, recht)

    @SuppressLint("BatteryLife")   // die App muss im Hintergrund starten dürfen, das ist ihr Zweck
    private fun berechtigungen() {
        val erst = listOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.POST_NOTIFICATIONS).filterNot { hat(it) }
        when {
            erst.isNotEmpty() -> requestPermissions(erst.toTypedArray(), 1)
            !hat(Manifest.permission.ACCESS_BACKGROUND_LOCATION) -> {
                Toast.makeText(this, "Bitte „Immer zulassen“ wählen.", Toast.LENGTH_LONG).show()
                requestPermissions(arrayOf(Manifest.permission.ACCESS_BACKGROUND_LOCATION), 2)
            }
            !Rechte.akkuFrei(this) -> startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                Uri.parse("package:$packageName")))
            !Rechte.bleiben(this) -> {
                Toast.makeText(this, "Bitte „App-Aktivität pausieren, wenn nicht verwendet“ ausschalten.", Toast.LENGTH_LONG).show()
                startActivity(Intent(Intent.ACTION_AUTO_REVOKE_PERMISSIONS, Uri.parse("package:$packageName")))
            }
            else -> Toast.makeText(this, "Alles erteilt.", Toast.LENGTH_SHORT).show()
        }
    }

    @SuppressLint("MissingPermission")   // geprüft über hat()
    private fun autoWaehlen() {
        if (!hat(Manifest.permission.BLUETOOTH_CONNECT)) {
            Toast.makeText(this, "Zuerst die Berechtigungen erteilen.", Toast.LENGTH_LONG).show()
            return
        }
        val geraete = getSystemService(BluetoothManager::class.java).adapter?.bondedDevices
            ?.sortedBy { it.name ?: it.address } ?: emptyList()
        if (geraete.isEmpty()) {
            Toast.makeText(this, "Keine gekoppelten Bluetooth-Geräte gefunden.", Toast.LENGTH_LONG).show()
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Welches Gerät ist das Auto?")
            .setItems(geraete.map { it.name ?: it.address }.toTypedArray()) { _, i ->
                speicher.autoAdresse = geraete[i].address
                speicher.autoName = geraete[i].name ?: geraete[i].address
                anzeigen()
            }
            .setNegativeButton("Abbrechen", null)
            .show()
    }

    // --- Anzeige ---

    private fun anzeigen() {
        val db = Datenbank.von(this)
        val offen = db.offeneFahrt()
        val heute = LocalDate.now()
        val etappen = speicher.etappen()
        val zeilen = mutableListOf<String>()
        when (offen?.zustand) {
            Zustand.LAEUFT -> zeilen += "● Aufzeichnung läuft seit ${zeit(offen.beginn)}."
            Zustand.PAUSE -> zeilen += "Ⅱ Pause – die Fahrt geht weiter, sobald das Auto wieder verbunden ist."
            else -> {}
        }
        val ziele = Regeln.heutigeZiele(heute, etappen)
        if (ziele.isNotEmpty()) {
            zeilen += "Heute ist ein Etappentag. Ziel: " + ziele.joinToString(", ") { it.name + if (it.breite == null) " (ohne Koordinaten!)" else "" }
        } else {
            val naechste = Regeln.naechste(heute, etappen)
            zeilen += if (naechste != null) "Nächste Etappe: ${tag.format(naechste.datum)} ${naechste.von.name} → ${naechste.nach.name}"
            else if (speicher.stand != 0L) "Keine Etappe in den nächsten 30 Tagen." else ""
        }
        findViewById<TextView>(R.id.status).text = zeilen.filter { it.isNotEmpty() }.joinToString("\n")
        findViewById<Button>(R.id.starten).isEnabled = offen?.zustand != Zustand.LAEUFT
        findViewById<Button>(R.id.beenden).isEnabled = offen != null
        findViewById<Switch>(R.id.automatik).isChecked = speicher.automatik

        val update = speicher.update()
        findViewById<View>(R.id.update).visibility = if (update != null) View.VISIBLE else View.GONE
        if (update != null) {
            findViewById<TextView>(R.id.update_text).text =
                "Neue Version ${update.version} verfügbar (installiert: ${speicher.version})"
        }

        // Kurz immer sichtbar, was fehlt; die ganze Liste hinter „Details“.
        val haken = { ok: Boolean -> if (ok) "✓" else "✗" }
        val rechte = Rechte.alle(this)
        val fehlt = listOfNotNull(if (speicher.url == null) "Etappen-Link" else null,
            if (speicher.autoAdresse == null) "Auto gewählt" else null) + rechte.filterNot { it.erteilt }.map { it.name }
        val kurz = mutableListOf(if (fehlt.isEmpty()) "✓ Alles eingerichtet" else "✗ Es fehlt: " + fehlt.joinToString(", "))
        speicher.fehler?.let { kurz += "⚠ $it" }
        speicher.planFehler?.let { kurz += "⚠ Hintergrund-Abruf nicht eingeplant: $it" }
        findViewById<TextView>(R.id.einrichtung_kurz).text = kurz.joinToString("\n")

        val einrichtung = listOf(
            "${haken(speicher.url != null)} Etappen-Link" + (if (speicher.stand != 0L)
                " (Stand " + DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(speicher.stand)) + ")" else ""),
            "${haken(speicher.autoAdresse != null)} Auto: ${speicher.autoName ?: "noch nicht gewählt"}",
        ) + rechte.map { "${haken(it.erteilt)} ${it.name}" } + "App-Version: ${speicher.version}"
        findViewById<TextView>(R.id.einrichtung).text = einrichtung.joinToString("\n")
        findViewById<View>(R.id.details).visibility = if (detailsOffen) View.VISIBLE else View.GONE
        findViewById<Button>(R.id.details_knopf).text = if (detailsOffen) "Details ausblenden" else "Details anzeigen"

        val liste = findViewById<LinearLayout>(R.id.fahrten)
        liste.removeAllViews()
        val fahrten = db.fahrten()
        if (fahrten.isEmpty()) {
            liste.addView(TextView(this).apply { text = "Noch keine Fahrten."; alpha = 0.7f })
        }
        for (f in fahrten) {
            liste.addView(Button(this).apply {
                isAllCaps = false
                text = "${zeit(f.beginn)}${f.ziel?.let { " → $it" } ?: ""} · ${zustandText(f.zustand)}"
                setOnClickListener {
                    startActivity(Intent(this@MainActivity, FahrtActivity::class.java).putExtra(FahrtActivity.FAHRT, f.id))
                }
            })
        }
    }

    companion object {
        private val tag = DateTimeFormatter.ofPattern("EE dd.MM.", Locale.GERMAN)
        private val zeitpunkt = DateTimeFormatter.ofPattern("EE dd.MM. HH:mm", Locale.GERMAN)

        fun zeit(millis: Long): String = zeitpunkt.format(Instant.ofEpochMilli(millis).atZone(ZoneId.systemDefault()))

        fun zustandText(z: Zustand) = when (z) {
            Zustand.LAEUFT -> "läuft"
            Zustand.PAUSE -> "Pause"
            Zustand.FERTIG -> "prüfen"
            Zustand.GESPEICHERT -> "gespeichert"
        }
    }
}

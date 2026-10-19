package de.urlaubsplaner.widget

import android.graphics.Bitmap
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Was Widget und App gerade zeigen: Kreisbild, Beschriftung darunter und die nächste Reise. */
class Anzeige(val bild: Bitmap, val titel: String, val reise: Reise?) {
    companion object {
        fun aus(speicher: Speicher, jetzt: LocalDateTime = LocalDateTime.now()): Anzeige {
            if (speicher.url == null) return Anzeige(Kreis.bild("?", null, 0f), "Einrichten", null)
            val reise = speicher.naechste(jetzt)
                ?: return Anzeige(Kreis.bild("–", null, 0f),
                    if (speicher.stand == 0L) "Urlaub" else "Keine Reise", null)
            val heute = jetzt.toLocalDate()
            val tage = reise.tage(heute)
            val bild = if (tage <= 0) Kreis.bild("Heute", reise.uhrzeit?.let { "%02d:%02d".format(it.hour, it.minute) }, 1f)
            else Kreis.bild(tage.toString(), null, reise.anteil(heute))
            return Anzeige(bild, reise.titel, reise)
        }

        private val DATUM = DateTimeFormatter.ofPattern("EEEE, d. MMMM yyyy", Locale.GERMAN)

        fun beschreibung(reise: Reise, heute: LocalDate = LocalDate.now()): String {
            val tage = reise.tage(heute)
            val wann = DATUM.format(reise.datum) + (reise.uhrzeit?.let { ", %02d:%02d Uhr".format(it.hour, it.minute) } ?: "")
            val noch = when {
                tage <= 0L -> "Heute geht's los!"
                tage == 1L -> "Noch 1 Tag"
                else -> "Noch $tage Tage"
            }
            return "Nächste Reise: ${reise.titel}\nStart: $wann\n$noch"
        }
    }
}

package de.urlaubsplaner.tracking

import java.time.Duration
import java.time.LocalDate
import java.time.LocalTime
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

// Die Regeln der App ohne Android-Bezug, damit sie sich als Unit-Test prüfen lassen.

data class Ort(val name: String, val typ: String, val breite: Double?, val laenge: Double?)

data class Etappe(val reise: String, val datum: LocalDate, val startzeit: LocalTime?, val von: Ort, val nach: Ort)

/** Ein aufgezeichneter Standort; `zeit` in Millisekunden seit 1970 (UTC). */
data class Punkt(val zeit: Long, val breite: Double, val laenge: Double, val hoehe: Double?)

/** Ein Teilstück zwischen zwei Pausen (Auto verbunden → getrennt). */
data class Teil(val id: Long, val beginn: Long, val ende: Long?, val punkte: List<Punkt>) {
    val meter: Double get() = punkte.zipWithNext { a, b -> abstand(a.breite, a.laenge, b.breite, b.laenge) }.sum()
}

object Regeln {
    /** Ab diesem Abstand zum Etappenziel gilt das Trennen vom Auto als Ankunft. */
    const val ZIELRADIUS_M = 1500.0

    /** Pausen bis zu dieser Länge sind beim Speichern als „verbinden“ vorbelegt. */
    val VERBINDEN_BIS: Duration = Duration.ofHours(2)

    /** So lange darf eine Pause dauern, dann gilt die Fahrt als beendet. */
    val PAUSE_HOECHSTENS: Duration = Duration.ofHours(6)

    /** Ungenauere Standorte werden verworfen (Meter). */
    const val GENAUIGKEIT_M = 50f

    /** Gestartet wird nur an einem Tag, an dem eine Etappe beginnt – die Uhrzeit spielt keine Rolle. */
    fun etappentag(heute: LocalDate, etappen: List<Etappe>): Boolean = etappen.any { it.datum == heute }

    /**
     * Das Etappenziel in der Nähe, falls es eines gibt. Es zählen die Etappen ab dem Tag, an dem
     * die Fahrt begann – so kommt eine Fahrt über Mitternacht an, während der Platz der letzten
     * Nacht beim Tanken um die Ecke am nächsten Morgen nicht als Ziel gilt.
     */
    fun zielInDerNaehe(breite: Double, laenge: Double, beginn: LocalDate, heute: LocalDate, etappen: List<Etappe>,
                       radius: Double = ZIELRADIUS_M): Ort? =
        etappen.asSequence()
            .filter { !it.datum.isBefore(beginn) && !it.datum.isAfter(heute) }
            .map { it.nach }
            .filter { it.breite != null && it.laenge != null }
            .map { it to abstand(breite, laenge, it.breite!!, it.laenge!!) }
            .filter { it.second <= radius }
            .minByOrNull { it.second }
            ?.first

    /** Die heutigen Etappenziele – für die Anzeige in der App. */
    fun heutigeZiele(heute: LocalDate, etappen: List<Etappe>): List<Ort> =
        etappen.filter { it.datum == heute }.map { it.nach }

    /** Die nächste Etappe ab heute. */
    fun naechste(heute: LocalDate, etappen: List<Etappe>): Etappe? =
        etappen.filter { !it.datum.isBefore(heute) }.minByOrNull { it.datum }

    /** Vorbelegung der Schalter „mit dem vorigen verbinden“: kurze Pausen ja, lange nein. */
    fun verbindenVorschlag(teile: List<Teil>): List<Boolean> =
        teile.zipWithNext { a, b ->
            val pause = Duration.ofMillis(b.beginn - (a.ende ?: a.beginn))
            pause <= VERBINDEN_BIS
        }

    /**
     * Fasst die Teilstücke nach den Schaltern zusammen: `verbinden[i]` gilt zwischen Teil i und i+1.
     * Jede Gruppe wird eine Fahrt (eine GPX-Datei); innerhalb bleibt jedes Teilstück ein eigenes Segment.
     * Verworfene Teile fallen heraus; ihre Nachbarn bleiben getrennt, wenn einer der Schalter aus ist.
     */
    fun gruppieren(teile: List<Teil>, verbinden: List<Boolean>, behalten: List<Boolean>): List<List<Teil>> {
        val gruppen = mutableListOf<MutableList<Teil>>()
        var neu = true
        teile.forEachIndexed { i, teil ->
            if (i > 0 && !verbinden[i - 1]) neu = true
            if (!behalten[i]) return@forEachIndexed
            if (neu) gruppen += mutableListOf<Teil>()
            gruppen.last() += teil
            neu = false
        }
        return gruppen.filter { gruppe -> gruppe.any { it.punkte.isNotEmpty() } }
    }
}

/** Abstand zweier Punkte auf der Erde in Metern (Haversine). */
fun abstand(breite1: Double, laenge1: Double, breite2: Double, laenge2: Double): Double {
    val r = 6371000.0
    val p1 = Math.toRadians(breite1)
    val p2 = Math.toRadians(breite2)
    val dp = p2 - p1
    val dl = Math.toRadians(laenge2 - laenge1)
    val h = sin(dp / 2).pow(2) + cos(p1) * cos(p2) * sin(dl / 2).pow(2)
    return 2 * r * asin(sqrt(h))
}

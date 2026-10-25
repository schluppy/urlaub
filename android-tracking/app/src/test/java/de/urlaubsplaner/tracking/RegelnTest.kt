package de.urlaubsplaner.tracking

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneOffset

class RegelnTest {
    private val zuhause = Ort("Zuhause", "zuhause", 47.790191, 12.008675)
    private val brenner = Ort("Zwischenstopp", "zwischen", 46.95, 11.44)
    private val camping = Ort("Camping Toskana", "camping", 42.92, 10.53)
    private val ohne = Ort("Ohne Koordinaten", "camping", null, null)
    private val tag1 = LocalDate.of(2027, 8, 28)
    private val tag2 = tag1.plusDays(1)
    private val etappen = listOf(
        Etappe("Sommer", tag1, null, zuhause, brenner),
        Etappe("Sommer", tag2, null, brenner, camping),
    )

    @Test fun nurAnEtappentagen() {
        assertTrue(Regeln.etappentag(tag1, etappen))
        assertFalse(Regeln.etappentag(tag1.minusDays(1), etappen))
    }

    @Test fun rechteAmTagDavorUndAmEtappentag() {
        assertEquals(tag1, Regeln.rechtePruefen(tag1.minusDays(1), etappen)?.datum)
        assertEquals(tag1, Regeln.rechtePruefen(tag1, etappen)?.datum)
        assertNull(Regeln.rechtePruefen(tag1.minusDays(2), etappen))
        assertNull(Regeln.rechtePruefen(tag2.plusDays(1), etappen))
    }

    @Test fun zielInDerNaeheUndWeitWeg() {
        assertEquals(brenner, Regeln.zielInDerNaehe(46.955, 11.445, tag1, tag1, etappen))   // ca. 700 m
        assertNull(Regeln.zielInDerNaehe(46.98, 11.44, tag1, tag1, etappen))                // ca. 3,3 km
        assertNull(Regeln.zielInDerNaehe(42.92, 10.53, tag1, tag1, etappen))                // Ziel erst morgen
    }

    @Test fun fahrtUeberMitternachtKommtAnAberDerPlatzVonGesternZaehltMorgensNicht() {
        assertEquals(brenner, Regeln.zielInDerNaehe(46.95, 11.44, tag1, tag2, etappen))
        assertNull(Regeln.zielInDerNaehe(46.95, 11.44, tag2, tag2, etappen))
    }

    @Test fun zielOhneKoordinatenWirdUebergangen() {
        val mit = listOf(Etappe("Sommer", tag1, null, zuhause, ohne))
        assertNull(Regeln.zielInDerNaehe(42.92, 10.53, tag1, tag1, mit))
    }

    @Test fun abstandMuenchenInnsbruck() {
        val m = abstand(48.1374, 11.5755, 47.2692, 11.4041)
        assertTrue("$m", m in 96_000.0..98_000.0)
    }

    private fun zeit(stunde: Int, minute: Int = 0) = tag1.atTime(stunde, minute).toInstant(ZoneOffset.UTC).toEpochMilli()

    private fun teil(id: Long, von: Int, bis: Int, punkte: Int = 2) = Teil(id, zeit(von), zeit(bis),
        (0 until punkte).map { Punkt(zeit(von) + it * 1000L, 47.0 + it * 0.01, 11.0, null) })

    @Test fun kurzePausenVerbindenLangeNicht() {
        val teile = listOf(teil(1, 7, 9), teil(2, 10, 12), teil(3, 15, 18))
        assertEquals(listOf(true, false), Regeln.verbindenVorschlag(teile))
    }

    @Test fun gruppierenNachSchalternUndVerworfenen() {
        val a = teil(1, 7, 9); val b = teil(2, 10, 12); val c = teil(3, 13, 14); val d = teil(4, 15, 18)
        val teile = listOf(a, b, c, d)
        assertEquals(listOf(listOf(a, b, c, d)), Regeln.gruppieren(teile, listOf(true, true, true), listOf(true, true, true, true)))
        assertEquals(listOf(listOf(a, b), listOf(c, d)), Regeln.gruppieren(teile, listOf(true, false, true), listOf(true, true, true, true)))
        // verworfenes Teil in der Mitte: die Nachbarn bleiben zusammen, solange beide Schalter an sind
        assertEquals(listOf(listOf(a, c, d)), Regeln.gruppieren(teile, listOf(true, true, true), listOf(true, false, true, true)))
        assertEquals(listOf(listOf(a), listOf(c, d)), Regeln.gruppieren(teile, listOf(false, true, true), listOf(true, false, true, true)))
        assertEquals(emptyList<List<Teil>>(), Regeln.gruppieren(teile, listOf(true, true, true), listOf(false, false, false, false)))
    }

    @Test fun gpxMitSegmentJeTeilstueck() {
        val gpx = Gpx.schreiben("Fahrt <Test> & mehr", listOf(teil(1, 7, 9, 2), teil(2, 10, 12, 3), teil(3, 13, 14, 0)))
        assertEquals(2, Regex("<trkseg>").findAll(gpx).count())
        assertEquals(5, Regex("<trkpt ").findAll(gpx).count())
        assertTrue(gpx.contains("<name>Fahrt &lt;Test&gt; &amp; mehr</name>"))
        assertTrue(gpx.contains("<trkpt lat=\"47.0100000\" lon=\"11.0000000\"><time>2027-08-28T07:00:01Z</time></trkpt>"))
        assertEquals("Fahrt_2027-08-28_07-00.gpx", Gpx.name(listOf(teil(1, 7, 9)), ZoneOffset.UTC))
    }
}

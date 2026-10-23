package de.urlaubsplaner.tracking

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Schreibt eine Fahrt als GPX 1.1: ein Track, je Teilstück ein Segment. */
object Gpx {
    private val dateiZeit = DateTimeFormatter.ofPattern("yyyy-MM-dd_HH-mm")

    fun name(teile: List<Teil>, zone: ZoneId = ZoneId.systemDefault()): String =
        "Fahrt_" + dateiZeit.format(Instant.ofEpochMilli(teile.first().beginn).atZone(zone)) + ".gpx"

    fun schreiben(titel: String, teile: List<Teil>): String = buildString {
        append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
        append("<gpx version=\"1.1\" creator=\"Urlaubsplaner Tracking\" xmlns=\"http://www.topografix.com/GPX/1/1\">\n")
        append("  <metadata><name>").append(text(titel)).append("</name><time>")
            .append(Instant.ofEpochMilli(teile.first().beginn)).append("</time></metadata>\n")
        append("  <trk>\n    <name>").append(text(titel)).append("</name>\n")
        for (teil in teile) {
            if (teil.punkte.isEmpty()) continue
            append("    <trkseg>\n")
            for (p in teil.punkte) {
                append("      <trkpt lat=\"").append(zahl(p.breite, 7)).append("\" lon=\"").append(zahl(p.laenge, 7)).append("\">")
                p.hoehe?.let { append("<ele>").append(zahl(it, 1)).append("</ele>") }
                append("<time>").append(Instant.ofEpochMilli(p.zeit)).append("</time></trkpt>\n")
            }
            append("    </trkseg>\n")
        }
        append("  </trk>\n</gpx>\n")
    }

    private fun zahl(wert: Double, stellen: Int) = String.format(Locale.ROOT, "%.${stellen}f", wert)

    private fun text(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
}

package de.urlaubsplaner.widget

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.SweepGradient
import android.graphics.Typeface

/** Zeichnet den runden Countdown: Zahl in der Mitte, darunter klein ein Zusatz, außen der Fortschrittsring. */
object Kreis {
    private const val GROESSE = 360

    fun bild(text: String, zusatz: String?, anteil: Float): Bitmap {
        val bild = Bitmap.createBitmap(GROESSE, GROESSE, Bitmap.Config.ARGB_8888)
        val leinwand = Canvas(bild)
        val mitte = GROESSE / 2f
        val radius = mitte - 2f

        val flaeche = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#1E2B45") }
        leinwand.drawCircle(mitte, mitte, radius, flaeche)

        val breite = radius * 0.08f
        val ring = RectF(mitte - radius * 0.88f, mitte - radius * 0.88f, mitte + radius * 0.88f, mitte + radius * 0.88f)
        val spur = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE; strokeWidth = breite; color = Color.parseColor("#33FFFFFF")
        }
        leinwand.drawArc(ring, 0f, 360f, false, spur)
        if (anteil > 0f) {
            val verlauf = SweepGradient(mitte, mitte,
                intArrayOf(Color.parseColor("#4DD0E1"), Color.parseColor("#B388FF"), Color.parseColor("#F06292")),
                floatArrayOf(0f, 0.5f, 1f))
            verlauf.setLocalMatrix(Matrix().apply { setRotate(-90f, mitte, mitte) })
            val bogen = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                style = Paint.Style.STROKE; strokeWidth = breite; strokeCap = Paint.Cap.ROUND; shader = verlauf
            }
            leinwand.drawArc(ring, -90f, 360f * anteil, false, bogen)
        }

        val schrift = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textAlign = Paint.Align.CENTER
            typeface = Typeface.create("sans-serif", Typeface.NORMAL)
            textSize = when {
                text.length <= 2 -> radius * 0.75f
                text.length == 3 -> radius * 0.62f
                text.length == 4 -> radius * 0.48f
                else -> radius * 0.36f
            }
        }
        // Zu breite Texte verkleinern, damit sie im Ring bleiben
        val platz = radius * 1.4f
        val gemessen = schrift.measureText(text)
        if (gemessen > platz) schrift.textSize *= platz / gemessen
        val versatz = if (zusatz != null) -radius * 0.08f else 0f
        val grundlinie = mitte + versatz - (schrift.ascent() + schrift.descent()) / 2
        leinwand.drawText(text, mitte, grundlinie, schrift)

        if (zusatz != null) {
            val klein = Paint(schrift).apply { textSize = radius * 0.2f; alpha = 210 }
            leinwand.drawText(zusatz, mitte, grundlinie + radius * 0.3f, klein)
        }
        return bild
    }
}

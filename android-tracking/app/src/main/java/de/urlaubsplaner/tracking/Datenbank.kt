package de.urlaubsplaner.tracking

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/** Zustand einer Fahrt: läuft → (Pause ↔ läuft) → fertig → gespeichert. */
enum class Zustand { LAEUFT, PAUSE, FERTIG, GESPEICHERT }

data class Fahrt(val id: Long, val beginn: Long, val ende: Long?, val zustand: Zustand, val ziel: String?)

/**
 * Fahrten, Teilstücke und Standorte. Jeder Standort wird sofort geschrieben,
 * damit ein Absturz oder Neustart des Handys nichts verliert.
 */
class Datenbank private constructor(context: Context) :
    SQLiteOpenHelper(context.applicationContext, "tracking.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE fahrt (id INTEGER PRIMARY KEY, beginn INTEGER NOT NULL, ende INTEGER, zustand TEXT NOT NULL, ziel TEXT)")
        db.execSQL("CREATE TABLE teil (id INTEGER PRIMARY KEY, fahrt INTEGER NOT NULL, beginn INTEGER NOT NULL, ende INTEGER)")
        db.execSQL("CREATE TABLE punkt (teil INTEGER NOT NULL, zeit INTEGER NOT NULL, breite REAL NOT NULL, laenge REAL NOT NULL, hoehe REAL)")
        db.execSQL("CREATE INDEX punkt_teil ON punkt (teil, zeit)")
    }

    override fun onUpgrade(db: SQLiteDatabase, alt: Int, neu: Int) {}

    /** Die Fahrt, die gerade läuft oder pausiert. */
    fun offeneFahrt(): Fahrt? =
        fahrten("zustand IN ('LAEUFT', 'PAUSE')", null, 1).firstOrNull()

    fun fahrt(id: Long): Fahrt? = fahrten("id = ?", arrayOf(id.toString()), 1).firstOrNull()

    /** Die letzten Fahrten, neueste zuerst. */
    fun fahrten(anzahl: Int = 30): List<Fahrt> = fahrten(null, null, anzahl)

    private fun fahrten(wo: String?, args: Array<String>?, anzahl: Int): List<Fahrt> =
        readableDatabase.query("fahrt", null, wo, args, null, null, "beginn DESC", anzahl.toString()).use { c ->
            generateSequence { if (c.moveToNext()) c else null }.map {
                Fahrt(
                    id = it.getLong(0), beginn = it.getLong(1), ende = if (it.isNull(2)) null else it.getLong(2),
                    zustand = Zustand.valueOf(it.getString(3)), ziel = it.getString(4),
                )
            }.toList()
        }

    fun neueFahrt(jetzt: Long): Long =
        writableDatabase.insert("fahrt", null, ContentValues().apply {
            put("beginn", jetzt); put("zustand", Zustand.LAEUFT.name)
        })

    fun setzen(fahrt: Long, zustand: Zustand, ende: Long? = null, ziel: String? = null) {
        writableDatabase.update("fahrt", ContentValues().apply {
            put("zustand", zustand.name)
            if (ende != null) put("ende", ende)
            if (ziel != null) put("ziel", ziel)
        }, "id = ?", arrayOf(fahrt.toString()))
    }

    fun neuesTeil(fahrt: Long, jetzt: Long): Long =
        writableDatabase.insert("teil", null, ContentValues().apply { put("fahrt", fahrt); put("beginn", jetzt) })

    /** Das Teilstück, in das gerade aufgezeichnet wird. */
    fun offenesTeil(fahrt: Long): Long? =
        readableDatabase.rawQuery("SELECT id FROM teil WHERE fahrt = ? AND ende IS NULL ORDER BY beginn DESC LIMIT 1",
            arrayOf(fahrt.toString())).use { if (it.moveToFirst()) it.getLong(0) else null }

    fun teilBeenden(fahrt: Long, jetzt: Long) {
        writableDatabase.update("teil", ContentValues().apply { put("ende", jetzt) },
            "fahrt = ? AND ende IS NULL", arrayOf(fahrt.toString()))
    }

    fun punkt(teil: Long, p: Punkt) {
        writableDatabase.insert("punkt", null, ContentValues().apply {
            put("teil", teil); put("zeit", p.zeit); put("breite", p.breite); put("laenge", p.laenge)
            if (p.hoehe != null) put("hoehe", p.hoehe)
        })
    }

    /** Der letzte Standort der Fahrt – daran erkennt die App beim Trennen, ob sie am Ziel ist. */
    fun letzterPunkt(fahrt: Long): Punkt? =
        readableDatabase.rawQuery(
            "SELECT p.zeit, p.breite, p.laenge, p.hoehe FROM punkt p JOIN teil t ON t.id = p.teil " +
                "WHERE t.fahrt = ? ORDER BY p.zeit DESC LIMIT 1", arrayOf(fahrt.toString())
        ).use { if (it.moveToFirst()) Punkt(it.getLong(0), it.getDouble(1), it.getDouble(2), if (it.isNull(3)) null else it.getDouble(3)) else null }

    /** Das Ende des letzten Teilstücks – seit dann dauert die Pause. */
    fun pauseSeit(fahrt: Long): Long? =
        readableDatabase.rawQuery("SELECT MAX(ende) FROM teil WHERE fahrt = ?", arrayOf(fahrt.toString()))
            .use { if (it.moveToFirst() && !it.isNull(0)) it.getLong(0) else null }

    fun teile(fahrt: Long): List<Teil> {
        val koepfe = readableDatabase.rawQuery("SELECT id, beginn, ende FROM teil WHERE fahrt = ? ORDER BY beginn",
            arrayOf(fahrt.toString())).use { c ->
            generateSequence { if (c.moveToNext()) c else null }
                .map { Triple(it.getLong(0), it.getLong(1), if (it.isNull(2)) null else it.getLong(2)) }.toList()
        }
        return koepfe.map { (id, beginn, ende) ->
            val punkte = readableDatabase.rawQuery("SELECT zeit, breite, laenge, hoehe FROM punkt WHERE teil = ? ORDER BY zeit",
                arrayOf(id.toString())).use { c ->
                generateSequence { if (c.moveToNext()) c else null }
                    .map { Punkt(it.getLong(0), it.getDouble(1), it.getDouble(2), if (it.isNull(3)) null else it.getDouble(3)) }
                    .toList()
            }
            Teil(id, beginn, ende, punkte)
        }
    }

    fun loeschen(fahrt: Long) {
        writableDatabase.apply {
            beginTransaction()
            try {
                execSQL("DELETE FROM punkt WHERE teil IN (SELECT id FROM teil WHERE fahrt = ?)", arrayOf(fahrt))
                delete("teil", "fahrt = ?", arrayOf(fahrt.toString()))
                delete("fahrt", "id = ?", arrayOf(fahrt.toString()))
                setTransactionSuccessful()
            } finally {
                endTransaction()
            }
        }
    }

    companion object {
        @Volatile private var instanz: Datenbank? = null
        fun von(context: Context): Datenbank =
            instanz ?: synchronized(this) { instanz ?: Datenbank(context).also { instanz = it } }
    }
}

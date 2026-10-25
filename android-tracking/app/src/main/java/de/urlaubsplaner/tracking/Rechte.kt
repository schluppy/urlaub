package de.urlaubsplaner.tracking

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.PowerManager

/** Ein Recht, das die App für die automatische Aufzeichnung braucht, und ob Android es ihr gibt. */
data class Recht(val name: String, val erteilt: Boolean)

/**
 * Was Android der App erlaubt. Nach Monaten ohne Nutzung entzieht Android Berechtigungen und stoppt
 * den Hintergrund-Abruf – außer „App-Aktivität pausieren, wenn nicht verwendet“ ist ausgeschaltet.
 */
object Rechte {
    fun hat(context: Context, recht: String) = context.checkSelfPermission(recht) == PackageManager.PERMISSION_GRANTED

    fun akkuFrei(context: Context) =
        context.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(context.packageName)

    /** Android entzieht die Berechtigungen nicht, wenn die App lange nicht benutzt wird. */
    fun bleiben(context: Context) = context.packageManager.isAutoRevokeWhitelisted

    fun alle(context: Context) = listOf(
        Recht("Standort „immer“", hat(context, Manifest.permission.ACCESS_FINE_LOCATION) &&
            hat(context, Manifest.permission.ACCESS_BACKGROUND_LOCATION)),
        Recht("Geräte in der Nähe (Bluetooth)", hat(context, Manifest.permission.BLUETOOTH_CONNECT)),
        Recht("Benachrichtigungen", hat(context, Manifest.permission.POST_NOTIFICATIONS)),
        Recht("Akku-Optimierung aus", akkuFrei(context)),
        Recht("Nicht pausieren bei Nichtnutzung", bleiben(context)),
    )

    fun fehlend(context: Context) = alle(context).filterNot { it.erteilt }.map { it.name }
}

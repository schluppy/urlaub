package de.urlaubsplaner.tracking

import android.bluetooth.BluetoothDevice
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Hört auf das Auto: Android meldet das Verbinden und Trennen eines Bluetooth-Geräts auch,
 * wenn die App geschlossen ist. Dazu der Wecker nach einer langen Pause und der Neustart des Handys.
 */
class AutoEmpfaenger : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val aktion = intent.action ?: return
        if (aktion == Intent.ACTION_BOOT_COMPLETED) {
            AbrufDienst.planen(context)
            return
        }
        if (aktion == BluetoothDevice.ACTION_ACL_CONNECTED || aktion == BluetoothDevice.ACTION_ACL_DISCONNECTED) {
            val geraet = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java) ?: return
            val auto = Speicher(context).autoAdresse
            if (auto == null || !geraet.address.equals(auto, ignoreCase = true)) return
            Log.i("Tracking", "Auto ${if (aktion == BluetoothDevice.ACTION_ACL_CONNECTED) "verbunden" else "getrennt"}")
        }
        // Datenbank und Standorte nicht im Hauptthread – beim Beenden werden alle Punkte gelesen.
        val ergebnis = goAsync()
        Thread {
            try {
                when (aktion) {
                    BluetoothDevice.ACTION_ACL_CONNECTED -> Steuerung.verbunden(context)
                    BluetoothDevice.ACTION_ACL_DISCONNECTED -> Steuerung.getrennt(context)
                    Steuerung.PAUSE_VORBEI -> Steuerung.pauseVorbei(context)
                }
            } finally {
                ergebnis.finish()
            }
        }.start()
    }
}

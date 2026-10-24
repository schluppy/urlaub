package de.urlaubsplaner.widget

import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context

/**
 * Holt die Reisen im Hintergrund. Android startet den Job erst, wenn Netz da ist – auch im
 * Ruhemodus (Doze), wo ein Abruf direkt aus dem Widget keine Verbindung bekäme.
 * Schlägt der Abruf fehl, versucht Android es nach einer Wartezeit erneut.
 */
class AbrufDienst : JobService() {

    override fun onStartJob(params: JobParameters): Boolean {
        val speicher = Speicher(this)
        speicher.letzterJob = System.currentTimeMillis()
        if (speicher.url == null || System.currentTimeMillis() - speicher.stand < EIN_TAG) return false
        Thread {
            val erfolg = speicher.abrufen()
            WidgetProvider.zeichnen(this)
            jobFinished(params, !erfolg)
        }.start()
        return true
    }

    override fun onStopJob(params: JobParameters) = true   // Netz weg o. Ä. – später erneut versuchen

    companion object {
        private const val JOB_ID = 1
        private const val EIN_TAG = 20L * 60 * 60 * 1000   // etwas kürzer, damit der tägliche Abruf nicht knapp verpasst wird
        private const val ABSTAND = 4L * 60 * 60 * 1000    // so oft schaut der Job nach, ob ein Abruf fällig ist

        /** Den regelmäßigen Abruf einplanen, falls er noch nicht geplant ist. Darf App und Widget nie abstürzen lassen. */
        fun planen(context: Context) = try {
            val scheduler = context.getSystemService(JobScheduler::class.java)
            if (scheduler.getPendingJob(JOB_ID) == null) scheduler.schedule(
                JobInfo.Builder(JOB_ID, ComponentName(context, AbrufDienst::class.java))
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setPeriodic(ABSTAND)
                    .setBackoffCriteria(15L * 60 * 1000, JobInfo.BACKOFF_POLICY_EXPONENTIAL)
                    .setPersisted(true)   // übersteht einen Neustart des Handys
                    .build()
            )
            Speicher(context).planFehler = null
        } catch (e: Exception) {
            Speicher(context).planFehler = e.toString()
        }

        fun geplant(context: Context) = context.getSystemService(JobScheduler::class.java).getPendingJob(JOB_ID) != null

        fun abbrechen(context: Context) = context.getSystemService(JobScheduler::class.java).cancel(JOB_ID)
    }
}

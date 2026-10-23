package de.urlaubsplaner.tracking

import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context

/**
 * Holt die Etappen im Hintergrund. Android startet den Job erst, wenn Netz da ist – auch im
 * Ruhemodus (Doze).
 * Schlägt der Abruf fehl, versucht Android es nach einer Wartezeit erneut.
 */
class AbrufDienst : JobService() {

    override fun onStartJob(params: JobParameters): Boolean {
        val speicher = Speicher(this)
        if (speicher.url == null || System.currentTimeMillis() - speicher.stand < VERALTET) return false
        Thread {
            val erfolg = speicher.abrufen()
            jobFinished(params, !erfolg)
        }.start()
        return true
    }

    override fun onStopJob(params: JobParameters) = true   // Netz weg o. Ä. – später erneut versuchen

    companion object {
        private const val JOB_ID = 1
        private const val VERALTET = 6L * 60 * 60 * 1000    // öfter als beim Widget: kurz vor der Abfahrt ändert sich der Plan noch
        private const val ABSTAND = 2L * 60 * 60 * 1000    // so oft schaut der Job nach, ob ein Abruf fällig ist

        /** Den regelmäßigen Abruf einplanen, falls er noch nicht geplant ist. */
        fun planen(context: Context) {
            val scheduler = context.getSystemService(JobScheduler::class.java)
            if (scheduler.getPendingJob(JOB_ID) != null) return
            scheduler.schedule(
                JobInfo.Builder(JOB_ID, ComponentName(context, AbrufDienst::class.java))
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setPeriodic(ABSTAND)
                    .setBackoffCriteria(15L * 60 * 1000, JobInfo.BACKOFF_POLICY_EXPONENTIAL)
                    .setPersisted(true)   // übersteht einen Neustart des Handys
                    .build()
            )
        }

        fun abbrechen(context: Context) = context.getSystemService(JobScheduler::class.java).cancel(JOB_ID)
    }
}

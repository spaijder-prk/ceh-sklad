package ru.ceh.sklad.data.offline

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit
import ru.ceh.sklad.data.CehRepository
import ru.ceh.sklad.data.QueueAuthorizationException
import ru.ceh.sklad.data.QueueTemporaryException

class PendingOperationWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val repository = CehRepository(applicationContext)
        if (!repository.hasSession()) {
            return Result.success()
        }
        return try {
            when (repository.flushPendingOperations()) {
                FlushResult.COMPLETED -> Result.success()
                FlushResult.RETRY_LATER -> Result.retry()
                FlushResult.AUTH_REQUIRED -> Result.success()
            }
        } catch (_: QueueAuthorizationException) {
            Result.success()
        } catch (_: QueueTemporaryException) {
            Result.retry()
        }
    }

    companion object {
        private const val UNIQUE_WORK = "ceh-pending-operations-sync"

        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = OneTimeWorkRequestBuilder<PendingOperationWorker>()
                .setConstraints(constraints)
                .setBackoffCriteria(
                    BackoffPolicy.EXPONENTIAL,
                    30,
                    TimeUnit.SECONDS,
                )
                .build()
            WorkManager.getInstance(context.applicationContext).enqueueUniqueWork(
                UNIQUE_WORK,
                ExistingWorkPolicy.KEEP,
                request,
            )
        }
    }
}

enum class FlushResult {
    COMPLETED,
    RETRY_LATER,
    AUTH_REQUIRED,
}

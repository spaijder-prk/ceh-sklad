package ru.ceh.sklad.data

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

/**
 * Фоновая доставка не создает новых операций: она только повторяет уже сохраненные
 * запросы с тем же operation_key. Поэтому повтор после потери ответа безопасен.
 */
class PendingSyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val repository = WarehouseRepository(applicationContext)
        val user = repository.restoreSession() ?: return Result.success()
        if (user.id.isBlank()) return Result.success()

        return runCatching { repository.syncPendingOperations() }
            .fold(
                onSuccess = { sync ->
                    val unresolvedNetworkItems = sync.pending - sync.conflicts.size
                    if (unresolvedNetworkItems > 0) Result.retry() else Result.success()
                },
                onFailure = { Result.retry() },
            )
    }
}

object PendingSyncScheduler {
    private const val UNIQUE_WORK = "ceh-sklad-pending-sync"

    fun schedule(context: Context) {
        val request = OneTimeWorkRequestBuilder<PendingSyncWorker>()
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            )
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.SECONDS)
            .build()

        WorkManager.getInstance(context.applicationContext).enqueueUniqueWork(
            UNIQUE_WORK,
            ExistingWorkPolicy.KEEP,
            request,
        )
    }
}

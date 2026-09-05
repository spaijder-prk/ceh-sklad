package ru.ceh.sklad.data.offline

import android.content.Context
import androidx.room3.Dao
import androidx.room3.Database
import androidx.room3.Entity
import androidx.room3.PrimaryKey
import androidx.room3.Query
import androidx.room3.Room
import androidx.room3.RoomDatabase
import androidx.room3.Upsert

@Entity(tableName = "pending_operations")
data class PendingOperationEntity(
    @PrimaryKey val externalId: String,
    val operationType: String,
    val payloadJson: String,
    val createdAt: Long,
    val attempts: Int = 0,
    val status: String = STATUS_PENDING,
    val lastError: String? = null,
) {
    companion object {
        const val STATUS_PENDING = "pending"
        const val STATUS_FAILED = "failed"
        const val TYPE_SALE = "sale"
        const val TYPE_RETURN = "return"
    }
}

@Dao
interface PendingOperationDao {
    @Upsert
    suspend fun upsert(operation: PendingOperationEntity)

    @Query(
        "SELECT * FROM pending_operations " +
            "WHERE status = 'pending' ORDER BY createdAt ASC",
    )
    suspend fun pending(): List<PendingOperationEntity>

    @Query("DELETE FROM pending_operations WHERE externalId = :externalId")
    suspend fun delete(externalId: String)

    @Query(
        "UPDATE pending_operations SET attempts = attempts + 1, lastError = :message " +
            "WHERE externalId = :externalId",
    )
    suspend fun recordTemporaryFailure(externalId: String, message: String?)

    @Query(
        "UPDATE pending_operations SET status = 'failed', attempts = attempts + 1, " +
            "lastError = :message WHERE externalId = :externalId",
    )
    suspend fun markFailed(externalId: String, message: String?)

    @Query(
        "UPDATE pending_operations SET status = 'pending', lastError = NULL " +
            "WHERE status = 'failed'",
    )
    suspend fun retryFailed()

    @Query("SELECT COUNT(*) FROM pending_operations WHERE status = 'pending'")
    suspend fun pendingCount(): Int

    @Query("SELECT COUNT(*) FROM pending_operations WHERE status = 'failed'")
    suspend fun failedCount(): Int
}

@Database(
    entities = [PendingOperationEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class OfflineDatabase : RoomDatabase() {
    abstract fun pendingOperationDao(): PendingOperationDao

    companion object {
        @Volatile
        private var instance: OfflineDatabase? = null

        fun get(context: Context): OfflineDatabase = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext,
                OfflineDatabase::class.java,
                "ceh-offline.db",
            ).build().also { instance = it }
        }
    }
}

data class QueueStats(
    val pending: Int,
    val failed: Int,
)

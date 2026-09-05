package ru.ceh.sklad.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase

@Entity(tableName = "cached_snapshot")
data class CachedSnapshotEntity(
    @PrimaryKey val id: Int = 1,
    val stocksJson: String,
    val locationsJson: String,
    val debt: Double,
    val syncedAt: Long,
)

@Entity(
    tableName = "pending_operations",
    indices = [Index(value = ["userId"])],
)
data class PendingOperationEntity(
    @PrimaryKey val operationKey: String,
    val userId: String,
    val type: String,
    val payloadJson: String,
    val createdAt: Long,
    val lastError: String?,
)

@Dao
interface LocalDao {
    @Query("SELECT * FROM cached_snapshot WHERE id = 1 LIMIT 1")
    suspend fun snapshot(): CachedSnapshotEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun saveSnapshot(snapshot: CachedSnapshotEntity)

    @Query("DELETE FROM cached_snapshot")
    suspend fun clearSnapshot()

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun enqueue(operation: PendingOperationEntity): Long

    @Query("SELECT * FROM pending_operations WHERE userId = :userId ORDER BY createdAt")
    suspend fun pendingOperations(userId: String): List<PendingOperationEntity>

    @Query("SELECT COUNT(*) FROM pending_operations WHERE userId = :userId")
    suspend fun pendingCount(userId: String): Int

    @Query("DELETE FROM pending_operations WHERE operationKey = :operationKey")
    suspend fun removePending(operationKey: String)

    @Query("UPDATE pending_operations SET lastError = :message WHERE operationKey = :operationKey")
    suspend fun markPendingError(operationKey: String, message: String)
}

@Database(
    entities = [CachedSnapshotEntity::class, PendingOperationEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class LocalDatabase : RoomDatabase() {
    abstract fun localDao(): LocalDao

    companion object {
        @Volatile
        private var instance: LocalDatabase? = null

        fun get(context: Context): LocalDatabase = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext,
                LocalDatabase::class.java,
                "ceh_sklad_local.db",
            ).build().also { instance = it }
        }
    }
}

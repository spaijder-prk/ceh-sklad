package ru.ceh.sklad.data

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.google.gson.Gson

/**
 * JWT и данные текущего пользователя хранятся в защищенном хранилище через Android Keystore.
 * Последний подтвержденный снимок и очередь операций хранятся в Room.
 */
class AppStorage(context: Context) {
    private val gson = Gson()
    private val dao = LocalDatabase.get(context).localDao()
    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()
    private val secure = EncryptedSharedPreferences.create(
        context,
        "ceh_sklad_secure",
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    fun savedToken(): String? = secure.getString(KEY_TOKEN, null)

    fun saveSession(token: String, user: UserInfo) {
        secure.edit()
            .putString(KEY_TOKEN, token)
            .putString(KEY_USER, gson.toJson(user))
            .apply()
    }

    fun saveUser(user: UserInfo) {
        secure.edit().putString(KEY_USER, gson.toJson(user)).apply()
    }

    fun cachedUser(): UserInfo? = secure.getString(KEY_USER, null)?.let {
        runCatching { gson.fromJson(it, UserInfo::class.java) }.getOrNull()
    }

    suspend fun saveSnapshot(snapshot: CachedSnapshot) {
        dao.saveSnapshot(
            CachedSnapshotEntity(
                stocksJson = gson.toJson(snapshot.stocks),
                locationsJson = gson.toJson(snapshot.locations),
                debt = snapshot.debt,
                syncedAt = snapshot.syncedAt,
            )
        )
    }

    suspend fun cachedSnapshot(): CachedSnapshot? {
        val row = dao.snapshot() ?: return null
        return runCatching {
            CachedSnapshot(
                stocks = gson.fromJson(row.stocksJson, Array<StockItem>::class.java).toList(),
                locations = gson.fromJson(row.locationsJson, Array<LocationItem>::class.java).toList(),
                debt = row.debt,
                syncedAt = row.syncedAt,
            )
        }.getOrNull()
    }

    /** Выход удаляет авторизацию и снимок, но не теряет неподтвержденные операции. */
    suspend fun clearSession() {
        secure.edit().clear().apply()
        dao.clearSnapshot()
    }

    suspend fun enqueuePending(operation: PendingOperation) {
        dao.enqueue(operation.toEntity())
    }

    suspend fun pendingOperations(userId: String): List<PendingOperation> =
        dao.pendingOperations(userId).map { it.toModel() }

    suspend fun pendingCount(userId: String): Int = dao.pendingCount(userId)

    suspend fun removePending(operationKey: String) {
        dao.removePending(operationKey)
    }

    suspend fun markPendingError(operationKey: String, message: String) {
        dao.markPendingError(operationKey, message)
    }

    private fun PendingOperation.toEntity() = PendingOperationEntity(
        operationKey = operationKey,
        userId = userId,
        type = type,
        payloadJson = payloadJson,
        createdAt = createdAt,
        lastError = lastError,
    )

    private fun PendingOperationEntity.toModel() = PendingOperation(
        userId = userId,
        operationKey = operationKey,
        type = type,
        payloadJson = payloadJson,
        createdAt = createdAt,
        lastError = lastError,
    )

    private companion object {
        const val KEY_TOKEN = "access_token"
        const val KEY_USER = "current_user"
    }
}

data class CachedSnapshot(
    val stocks: List<StockItem>,
    val locations: List<LocationItem>,
    val debt: Double,
    val syncedAt: Long,
)

data class PendingOperation(
    val userId: String,
    val operationKey: String,
    val type: String,
    val payloadJson: String,
    val createdAt: Long,
    val lastError: String? = null,
)

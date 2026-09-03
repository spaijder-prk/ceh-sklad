package ru.ceh.sklad.data

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.google.gson.Gson

/**
 * Токен хранится через Android Keystore. Кэш остатков не является источником истины:
 * он нужен только для просмотра последнего подтвержденного сервером состояния без сети.
 */
class AppStorage(context: Context) {
    private val gson = Gson()
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
    private val cache = context.getSharedPreferences("ceh_sklad_cache", Context.MODE_PRIVATE)

    fun savedToken(): String? = secure.getString(KEY_TOKEN, null)

    fun saveSession(token: String, user: UserInfo) {
        secure.edit().putString(KEY_TOKEN, token).apply()
        cache.edit().putString(KEY_USER, gson.toJson(user)).apply()
    }

    fun saveUser(user: UserInfo) {
        cache.edit().putString(KEY_USER, gson.toJson(user)).apply()
    }

    fun cachedUser(): UserInfo? = cache.getString(KEY_USER, null)?.let {
        runCatching { gson.fromJson(it, UserInfo::class.java) }.getOrNull()
    }

    fun saveSnapshot(snapshot: CachedSnapshot) {
        cache.edit()
            .putString(KEY_STOCKS, gson.toJson(snapshot.stocks))
            .putString(KEY_LOCATIONS, gson.toJson(snapshot.locations))
            .putLong(KEY_SYNCED_AT, snapshot.syncedAt)
            .putString(KEY_DEBT, snapshot.debt.toString())
            .apply()
    }

    fun cachedSnapshot(): CachedSnapshot? {
        val syncedAt = cache.getLong(KEY_SYNCED_AT, 0L)
        val stocksJson = cache.getString(KEY_STOCKS, null) ?: return null
        val locationsJson = cache.getString(KEY_LOCATIONS, null) ?: return null
        if (syncedAt == 0L) return null
        return runCatching {
            CachedSnapshot(
                stocks = gson.fromJson(stocksJson, Array<StockItem>::class.java).toList(),
                locations = gson.fromJson(locationsJson, Array<LocationItem>::class.java).toList(),
                debt = cache.getString(KEY_DEBT, "0")?.toDoubleOrNull() ?: 0.0,
                syncedAt = syncedAt,
            )
        }.getOrNull()
    }

    fun clearSession() {
        secure.edit().clear().apply()
        cache.edit().clear().apply()
    }

    private companion object {
        const val KEY_TOKEN = "access_token"
        const val KEY_USER = "current_user"
        const val KEY_STOCKS = "stocks"
        const val KEY_LOCATIONS = "locations"
        const val KEY_DEBT = "debt"
        const val KEY_SYNCED_AT = "synced_at"
    }
}

data class CachedSnapshot(
    val stocks: List<StockItem>,
    val locations: List<LocationItem>,
    val debt: Double,
    val syncedAt: Long,
)

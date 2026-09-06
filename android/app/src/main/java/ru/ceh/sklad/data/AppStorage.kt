package ru.ceh.sklad.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.google.gson.Gson
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * JWT и профиль шифруются AES-GCM ключом из Android Keystore.
 * Последний подтвержденный снимок и очередь операций хранятся в Room;
 * резервное копирование приложения отключено в manifest.
 */
class AppStorage(context: Context) {
    private val gson = Gson()
    private val dao = LocalDatabase.get(context).localDao()
    private val securePrefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val secretKey: SecretKey by lazy { loadOrCreateKey() }

    fun savedToken(): String? = readEncrypted(KEY_TOKEN)

    fun saveSession(token: String, user: UserInfo) {
        securePrefs.edit()
            .putString(KEY_TOKEN, encrypt(token))
            .putString(KEY_USER, encrypt(gson.toJson(user)))
            .apply()
    }

    fun saveUser(user: UserInfo) {
        securePrefs.edit().putString(KEY_USER, encrypt(gson.toJson(user))).apply()
    }

    fun cachedUser(): UserInfo? = readEncrypted(KEY_USER)?.let {
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
        securePrefs.edit().clear().apply()
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

    private fun readEncrypted(key: String): String? {
        val encrypted = securePrefs.getString(key, null) ?: return null
        return runCatching { decrypt(encrypted) }
            .onFailure { securePrefs.edit().remove(key).apply() }
            .getOrNull()
    }

    private fun encrypt(value: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey)
        val ciphertext = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val iv = Base64.encodeToString(cipher.iv, Base64.NO_WRAP)
        val body = Base64.encodeToString(ciphertext, Base64.NO_WRAP)
        return "$iv.$body"
    }

    private fun decrypt(value: String): String {
        val parts = value.split('.', limit = 2)
        require(parts.size == 2) { "Некорректный формат защищенного значения" }
        val iv = Base64.decode(parts[0], Base64.NO_WRAP)
        val ciphertext = Base64.decode(parts[1], Base64.NO_WRAP)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, secretKey, GCMParameterSpec(GCM_TAG_BITS, iv))
        return cipher.doFinal(ciphertext).toString(Charsets.UTF_8)
    }

    private fun loadOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEY_STORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
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
        const val PREFS_NAME = "ceh_sklad_secure"
        const val KEY_TOKEN = "access_token"
        const val KEY_USER = "current_user"
        const val KEY_ALIAS = "ceh_sklad_session_key"
        const val ANDROID_KEY_STORE = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_TAG_BITS = 128
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

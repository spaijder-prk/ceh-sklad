package ru.ceh.sklad.data

import android.content.Context
import android.os.Handler
import android.os.Looper
import com.google.gson.Gson
import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import ru.ceh.sklad.BuildConfig

class WarehouseRepository(context: Context) {
    private val appContext = context.applicationContext
    private val storage = AppStorage(appContext)
    private val gson = Gson()
    private var token: String? = storage.savedToken()
    private var activeUserId: String? = storage.cachedUser()?.takeIf { isMobileRepresentative(it) }?.id

    private val client = OkHttpClient.Builder()
        .pingInterval(25, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val request = chain.request().newBuilder().apply {
                token?.let { header("Authorization", "Bearer $it") }
            }.build()
            chain.proceed(request)
        }
        .build()

    private val api: WarehouseApi = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(client)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(WarehouseApi::class.java)

    suspend fun login(login: String, password: String): UserInfo {
        val response = try {
            api.login(LoginRequest(login, password))
        } catch (_: IOException) {
            throw LoginRejectedException("Нет связи с сервером. Проверьте интернет и повторите попытку.")
        } catch (error: HttpException) {
            val retryAfter = error.response()?.headers()?.get("Retry-After")
            throw LoginRejectedException(loginErrorMessage(error.code(), retryAfter))
        }

        token = response.access_token
        return try {
            val user = requireMobileRepresentative(api.me())
            activeUserId = user.id
            storage.saveSession(response.access_token, user)
            user
        } catch (error: MobileSessionRejectedException) {
            logout()
            throw error
        } catch (_: IOException) {
            token = null
            throw LoginRejectedException("Вход подтвержден, но профиль не загрузился. Проверьте связь и повторите попытку.")
        } catch (error: HttpException) {
            token = null
            throw LoginRejectedException(
                if (error.code() == 401) {
                    "Сессия входа не подтверждена. Повторите попытку."
                } else {
                    "Не удалось завершить вход. Сервер вернул HTTP ${error.code()}."
                }
            )
        }
    }

    suspend fun restoreSession(): UserInfo? {
        if (token == null) return null
        return try {
            val user = api.me()
            if (!isMobileRepresentative(user)) {
                logout()
                null
            } else {
                activeUserId = user.id
                storage.saveUser(user)
                user
            }
        } catch (error: HttpException) {
            if (error.code() == 401) {
                logout()
                null
            } else {
                restoreValidCachedUser()
            }
        } catch (_: Exception) {
            restoreValidCachedUser()
        }
    }

    private suspend fun restoreValidCachedUser(): UserInfo? {
        val cached = storage.cachedUser()
        return if (isMobileRepresentative(cached)) {
            activeUserId = cached!!.id
            cached
        } else {
            logout()
            null
        }
    }

    suspend fun logout() {
        token = null
        activeUserId = null
        storage.clearSession()
    }

    suspend fun loadSnapshot(locationId: String?): CachedSnapshot {
        val stocks = api.getStocks()
        val locations = api.getLocations()
        val debt = locationId?.let { api.getDebt(it).debt } ?: 0.0
        return CachedSnapshot(stocks, locations, debt, System.currentTimeMillis()).also { storage.saveSnapshot(it) }
    }

    suspend fun loadHistory(limit: Int = 60): RepresentativeHistory = RepresentativeHistory(
        stock = api.getStockOperations(limit),
        money = api.getMoneyOperations(limit),
    )

    suspend fun changePassword(currentPassword: String, newPassword: String): String {
        return try {
            val result = api.changePassword(PasswordChangeRequest(currentPassword, newPassword))
            logout()
            result.message
        } catch (error: HttpException) {
            throw OperationRejectedException(operationErrorMessage(error))
        }
    }

    suspend fun cachedSnapshot(): CachedSnapshot? = storage.cachedSnapshot()
    suspend fun pendingCount(): Int = activeUserId?.let { storage.pendingCount(it) } ?: 0

    suspend fun discardPending(operationKey: String) {
        storage.removePending(operationKey)
    }

    suspend fun createSale(request: SaleRequest): SubmissionResult {
        val prepared = request.copy(operation_key = request.operation_key ?: UUID.randomUUID().toString())
        return submitOrQueue(TYPE_SALE, prepared.operation_key!!, prepared) { api.createSale(prepared) }
    }

    suspend fun returnGoods(request: TransferRequest): SubmissionResult {
        val prepared = request.copy(operation_key = request.operation_key ?: UUID.randomUUID().toString())
        return submitOrQueue(TYPE_RETURN, prepared.operation_key!!, prepared) { api.returnGoods(prepared) }
    }

    suspend fun handoverCash(request: CashHandoverRequest): SubmissionResult {
        val prepared = request.copy(operation_key = request.operation_key ?: UUID.randomUUID().toString())
        return submitOrQueue(TYPE_CASH, prepared.operation_key!!, prepared) { api.handoverCash(prepared) }
    }

    private suspend fun submitOrQueue(
        type: String,
        operationKey: String,
        payload: Any,
        send: suspend () -> OperationResult,
    ): SubmissionResult {
        return try {
            val result = send()
            storage.removePending(operationKey)
            SubmissionResult(true, result.message, operationKey)
        } catch (_: IOException) {
            queueOperation(type, operationKey, payload)
        } catch (error: HttpException) {
            if (error.code() >= 500) {
                queueOperation(type, operationKey, payload)
            } else {
                throw OperationRejectedException(operationErrorMessage(error))
            }
        }
    }

    private fun operationErrorMessage(error: HttpException): String {
        val detail = runCatching {
            val raw = error.response()?.errorBody()?.string()
            if (raw.isNullOrBlank()) null else gson.fromJson(raw, ApiError::class.java)?.detail
        }.getOrNull()
        return detail ?: when (error.code()) {
            401 -> "Сессия истекла. Войдите снова."
            403 -> "Недостаточно прав для этой операции."
            409 -> "Операция конфликтует с текущим состоянием на сервере. Обновите данные."
            422 -> "Проверьте введенные данные операции."
            else -> "Сервер отклонил операцию: HTTP ${error.code()}"
        }
    }

    private suspend fun queueOperation(type: String, operationKey: String, payload: Any): SubmissionResult {
        val userId = activeUserId ?: error("Нет активного пользователя для очереди операций")
        storage.enqueuePending(
            PendingOperation(
                userId = userId,
                operationKey = operationKey,
                type = type,
                payloadJson = gson.toJson(payload),
                createdAt = System.currentTimeMillis(),
            )
        )
        PendingSyncScheduler.schedule(appContext)
        return SubmissionResult(
            confirmed = false,
            message = "Нет подтверждения сервера. Операция сохранена в очередь и пока НЕ проведена.",
            operationKey = operationKey,
        )
    }

    suspend fun syncPendingOperations(): PendingSyncResult {
        val userId = activeUserId ?: return PendingSyncResult(0, 0, emptyList())
        val rows = storage.pendingOperations(userId)
        val conflicts = linkedMapOf<String, PendingConflict>()
        rows.filter { it.lastError != null }.forEach {
            conflicts[it.operationKey] = PendingConflict(it.operationKey, it.lastError!!)
        }
        var sent = 0

        for (row in rows) {
            try {
                when (row.type) {
                    TYPE_SALE -> api.createSale(gson.fromJson(row.payloadJson, SaleRequest::class.java))
                    TYPE_RETURN -> api.returnGoods(gson.fromJson(row.payloadJson, TransferRequest::class.java))
                    TYPE_CASH -> api.handoverCash(gson.fromJson(row.payloadJson, CashHandoverRequest::class.java))
                    else -> {
                        val message = "Неизвестный тип локальной операции: ${row.type}"
                        storage.markPendingError(row.operationKey, message)
                        conflicts[row.operationKey] = PendingConflict(row.operationKey, message)
                        continue
                    }
                }
                storage.removePending(row.operationKey)
                conflicts.remove(row.operationKey)
                sent += 1
            } catch (_: IOException) {
                break
            } catch (error: HttpException) {
                if (error.code() == 401) throw error
                if (error.code() in setOf(403, 404, 409, 422)) {
                    val message = operationErrorMessage(error)
                    storage.markPendingError(row.operationKey, message)
                    conflicts[row.operationKey] = PendingConflict(row.operationKey, message)
                    continue
                }
                if (error.code() >= 500) break
                val message = operationErrorMessage(error)
                storage.markPendingError(row.operationKey, message)
                conflicts[row.operationKey] = PendingConflict(row.operationKey, message)
            }
        }

        return PendingSyncResult(sent, storage.pendingCount(userId), conflicts.values.toList())
    }

    fun connectRealtime(onRefreshNeeded: () -> Unit): RealtimeSubscription? {
        val currentToken = token ?: return null
        val wsBase = BuildConfig.API_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
        val request = Request.Builder().url("${wsBase}api/v1/realtime?token=$currentToken").build()
        return RealtimeSubscription(client, request, onRefreshNeeded)
    }

    private data class ApiError(val detail: String?)

    private companion object {
        const val TYPE_SALE = "sale"
        const val TYPE_RETURN = "representative_return"
        const val TYPE_CASH = "cash_handover"
    }
}

internal fun loginErrorMessage(statusCode: Int, retryAfterHeader: String?): String {
    return when (statusCode) {
        401 -> "Неверный логин или пароль."
        429 -> retryAfterHeader
            ?.trim()
            ?.toLongOrNull()
            ?.coerceAtLeast(1L)
            ?.let { seconds -> "Слишком много попыток входа. Повторите через $seconds сек." }
            ?: "Слишком много попыток входа. Повторите позже."
        in 500..599 -> "Сервер временно недоступен. Повторите попытку позже."
        else -> "Не удалось войти. Сервер вернул HTTP $statusCode."
    }
}

class LoginRejectedException(message: String) : IllegalStateException(message)
class OperationRejectedException(message: String) : IllegalStateException(message)

class RealtimeSubscription(
    private val client: OkHttpClient,
    private val request: Request,
    private val onRefreshNeeded: () -> Unit,
) {
    private val handler = Handler(Looper.getMainLooper())
    private val stopped = AtomicBoolean(false)
    private var socket: WebSocket? = null
    private val reconnect = Runnable { open() }

    init {
        open()
    }

    private fun open() {
        if (stopped.get()) return
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                onRefreshNeeded()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                if (text.contains("stock_changed")) onRefreshNeeded()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                scheduleReconnect()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                if (code !in setOf(4401, 4403)) scheduleReconnect()
            }
        })
    }

    private fun scheduleReconnect() {
        if (stopped.get()) return
        handler.removeCallbacks(reconnect)
        handler.postDelayed(reconnect, 3_000L)
    }

    fun close() {
        if (!stopped.compareAndSet(false, true)) return
        handler.removeCallbacksAndMessages(null)
        socket?.close(1000, "Закрытие экрана")
        socket = null
    }
}

package ru.ceh.sklad.data

import android.content.Context
import com.google.gson.Gson
import java.io.IOException
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import ru.ceh.sklad.BuildConfig
import ru.ceh.sklad.data.offline.FlushResult
import ru.ceh.sklad.data.offline.OfflineDatabase
import ru.ceh.sklad.data.offline.PendingOperationEntity
import ru.ceh.sklad.data.offline.PendingOperationWorker
import ru.ceh.sklad.data.offline.QueueStats

class CehRepository(context: Context) {
    private val appContext = context.applicationContext
    private val tokenStore = TokenStore(appContext)
    private val gson = Gson()
    private val pendingDao = OfflineDatabase.get(appContext).pendingOperationDao()

    private val httpClient = OkHttpClient.Builder()
        .addInterceptor { chain ->
            val token = tokenStore.getToken()
            val request = if (token.isNullOrBlank()) {
                chain.request()
            } else {
                chain.request().newBuilder()
                    .header("Authorization", "Bearer $token")
                    .build()
            }
            chain.proceed(request)
        }
        .build()

    private val api: CehApi = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(httpClient)
        .addConverterFactory(GsonConverterFactory.create(gson))
        .build()
        .create(CehApi::class.java)

    fun hasSession(): Boolean = !tokenStore.getToken().isNullOrBlank()

    suspend fun login(email: String, password: String) {
        val token = api.login(email.trim(), password).accessToken
        tokenStore.saveToken(token)
        schedulePendingSync()
    }

    fun logout() {
        tokenStore.clear()
    }

    suspend fun loadDashboard(): DashboardData {
        val user = api.currentUser()
        val warehouses = api.warehouses()
        val warehouseBalances = api.warehouseBalances()

        if (user.role != ROLE_REPRESENTATIVE) {
            return DashboardData(
                user = user,
                representative = null,
                warehouses = warehouses,
                warehouseBalances = warehouseBalances,
                representativeBalances = emptyList(),
                debt = null,
                documents = emptyList(),
            )
        }

        val representative = api.representatives().firstOrNull { it.userId == user.id }
            ?: error("Учетная запись не привязана к торговому представителю")
        val ownBalances = api.representativeBalances(representative.id)
        val debt = api.representativeDebt(representative.id).debt
        val documents = api.myDocuments()

        return DashboardData(
            user = user,
            representative = representative,
            warehouses = warehouses,
            warehouseBalances = warehouseBalances,
            representativeBalances = ownBalances,
            debt = debt,
            documents = documents,
        )
    }

    suspend fun registerSale(request: SaleRequestDto): OperationResultDto = api.registerSale(request)

    suspend fun registerReturn(request: ReturnRequestDto): OperationResultDto = api.registerReturn(request)

    suspend fun enqueueSale(request: SaleRequestDto) {
        val externalId = requireNotNull(request.externalId) {
            "Для офлайн-продажи обязателен external_id"
        }
        pendingDao.upsert(
            PendingOperationEntity(
                externalId = externalId,
                operationType = PendingOperationEntity.TYPE_SALE,
                payloadJson = gson.toJson(request),
                createdAt = System.currentTimeMillis(),
            ),
        )
        schedulePendingSync()
    }

    suspend fun enqueueReturn(request: ReturnRequestDto) {
        val externalId = requireNotNull(request.externalId) {
            "Для офлайн-возврата обязателен external_id"
        }
        pendingDao.upsert(
            PendingOperationEntity(
                externalId = externalId,
                operationType = PendingOperationEntity.TYPE_RETURN,
                payloadJson = gson.toJson(request),
                createdAt = System.currentTimeMillis(),
            ),
        )
        schedulePendingSync()
    }

    suspend fun queueStats(): QueueStats = QueueStats(
        pending = pendingDao.pendingCount(),
        failed = pendingDao.failedCount(),
    )

    suspend fun retryFailedOperations() {
        pendingDao.retryFailed()
        schedulePendingSync()
    }

    fun schedulePendingSync() {
        PendingOperationWorker.schedule(appContext)
    }

    suspend fun flushPendingOperations(): FlushResult {
        for (operation in pendingDao.pending()) {
            try {
                when (operation.operationType) {
                    PendingOperationEntity.TYPE_SALE -> api.registerSale(
                        gson.fromJson(operation.payloadJson, SaleRequestDto::class.java),
                    )
                    PendingOperationEntity.TYPE_RETURN -> api.registerReturn(
                        gson.fromJson(operation.payloadJson, ReturnRequestDto::class.java),
                    )
                    else -> {
                        pendingDao.markFailed(operation.externalId, "Неизвестный тип операции")
                        continue
                    }
                }
                pendingDao.delete(operation.externalId)
            } catch (error: HttpException) {
                when {
                    error.code() == 401 -> return FlushResult.AUTH_REQUIRED
                    error.code() == 408 || error.code() == 429 || error.code() >= 500 -> {
                        pendingDao.recordTemporaryFailure(
                            operation.externalId,
                            "HTTP ${error.code()}",
                        )
                        return FlushResult.RETRY_LATER
                    }
                    else -> pendingDao.markFailed(
                        operation.externalId,
                        "Сервер отклонил операцию: HTTP ${error.code()}",
                    )
                }
            } catch (error: IOException) {
                pendingDao.recordTemporaryFailure(operation.externalId, error.message)
                return FlushResult.RETRY_LATER
            } catch (error: Exception) {
                pendingDao.markFailed(
                    operation.externalId,
                    error.message ?: "Не удалось разобрать сохраненную операцию",
                )
            }
        }
        return FlushResult.COMPLETED
    }

    fun openUpdates(
        onChanged: () -> Unit,
        onFailure: (Throwable) -> Unit,
    ): WebSocket? {
        val token = tokenStore.getToken() ?: return null
        val webSocketUrl = BuildConfig.API_BASE_URL
            .replaceFirst("https://", "wss://")
            .replaceFirst("http://", "ws://")
            .trimEnd('/') + "/api/v1/ws/updates"

        val request = Request.Builder()
            .url(webSocketUrl)
            .header("Authorization", "Bearer $token")
            .build()

        return httpClient.newWebSocket(
            request,
            object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) {
                    if (text.contains("\"state_changed\"") || text.contains("\"catalog_changed\"")) {
                        onChanged()
                    }
                }

                override fun onFailure(
                    webSocket: WebSocket,
                    t: Throwable,
                    response: Response?,
                ) {
                    onFailure(t)
                }
            },
        )
    }

    private companion object {
        const val ROLE_REPRESENTATIVE = "representative"
    }
}

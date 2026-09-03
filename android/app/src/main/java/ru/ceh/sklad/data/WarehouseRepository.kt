package ru.ceh.sklad.data

import android.content.Context
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
    private val storage = AppStorage(context)
    private var token: String? = storage.savedToken()

    private val client = OkHttpClient.Builder()
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
        val response = api.login(LoginRequest(login, password))
        token = response.access_token
        val user = api.me()
        storage.saveSession(response.access_token, user)
        return user
    }

    /**
     * При отсутствии сети разрешаем открыть только последний локальный снимок.
     * Если сервер явно вернул 401, локальная сессия удаляется.
     */
    suspend fun restoreSession(): UserInfo? {
        if (token == null) return null
        return try {
            api.me().also(storage::saveUser)
        } catch (error: HttpException) {
            if (error.code() == 401) {
                logout()
                null
            } else {
                storage.cachedUser()
            }
        } catch (_: Exception) {
            storage.cachedUser()
        }
    }

    fun logout() {
        token = null
        storage.clearSession()
    }

    suspend fun loadSnapshot(locationId: String?): CachedSnapshot {
        val stocks = api.getStocks()
        val locations = api.getLocations()
        val debt = locationId?.let { api.getDebt(it).debt } ?: 0.0
        return CachedSnapshot(stocks, locations, debt, System.currentTimeMillis()).also(storage::saveSnapshot)
    }

    fun cachedSnapshot(): CachedSnapshot? = storage.cachedSnapshot()

    suspend fun createSale(request: SaleRequest): OperationResult = api.createSale(request)
    suspend fun returnGoods(request: TransferRequest): OperationResult = api.returnGoods(request)
    suspend fun handoverCash(request: CashHandoverRequest): OperationResult = api.handoverCash(request)

    fun connectRealtime(onStockChanged: () -> Unit): WebSocket? {
        val currentToken = token ?: return null
        val wsBase = BuildConfig.API_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
        val request = Request.Builder().url("${wsBase}api/v1/realtime?token=$currentToken").build()
        return client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                if (text.contains("stock_changed")) onStockChanged()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                // Пользователь продолжит видеть последний подтвержденный снимок; ручное обновление повторит запрос.
            }
        })
    }
}

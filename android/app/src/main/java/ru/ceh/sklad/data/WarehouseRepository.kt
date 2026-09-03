package ru.ceh.sklad.data

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import ru.ceh.sklad.BuildConfig

class WarehouseRepository {
    private var token: String? = null

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
        token = api.login(LoginRequest(login, password)).access_token
        return api.me()
    }

    fun logout() {
        token = null
    }

    suspend fun loadStocks(): List<StockItem> = api.getStocks()
    suspend fun loadLocations(): List<LocationItem> = api.getLocations()
    suspend fun loadDebt(locationId: String): Double = api.getDebt(locationId).debt
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
                // Повторное подключение будет выполнено после следующего входа пользователя.
            }
        })
    }
}

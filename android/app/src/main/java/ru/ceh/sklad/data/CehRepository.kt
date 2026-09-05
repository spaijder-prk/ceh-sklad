package ru.ceh.sklad.data

import android.content.Context
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import ru.ceh.sklad.BuildConfig

class CehRepository(context: Context) {
    private val tokenStore = TokenStore(context.applicationContext)

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
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(CehApi::class.java)

    fun hasSession(): Boolean = !tokenStore.getToken().isNullOrBlank()

    suspend fun login(email: String, password: String) {
        val token = api.login(email.trim(), password).accessToken
        tokenStore.saveToken(token)
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
package ru.ceh.sklad.data

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface WarehouseApi {
    @POST("api/v1/auth/login")
    suspend fun login(@Body request: LoginRequest): TokenResponse

    @GET("api/v1/auth/me")
    suspend fun me(): UserInfo

    @POST("api/v1/auth/change-password")
    suspend fun changePassword(@Body request: PasswordChangeRequest): PasswordOperationResponse

    @GET("api/v1/locations")
    suspend fun getLocations(): List<LocationItem>

    @GET("api/v1/stocks")
    suspend fun getStocks(@Query("location_id") locationId: String? = null): List<StockItem>

    @POST("api/v1/sales")
    suspend fun createSale(@Body request: SaleRequest): OperationResult

    @POST("api/v1/stock/representative-return")
    suspend fun returnGoods(@Body request: TransferRequest): OperationResult

    @POST("api/v1/cash-handovers")
    suspend fun handoverCash(@Body request: CashHandoverRequest): OperationResult

    @GET("api/v1/representatives/{locationId}/debt")
    suspend fun getDebt(@Path("locationId") locationId: String): DebtResponse

    @GET("api/v1/operations/stock")
    suspend fun getStockOperations(@Query("limit") limit: Int = 60): List<StockOperation>

    @GET("api/v1/operations/money")
    suspend fun getMoneyOperations(@Query("limit") limit: Int = 60): List<MoneyOperation>
}

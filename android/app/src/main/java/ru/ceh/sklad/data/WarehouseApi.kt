package ru.ceh.sklad.data

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

interface WarehouseApi {
    @GET("api/v1/stocks")
    suspend fun getStocks(@Query("location_id") locationId: String? = null): List<StockItem>

    @POST("api/v1/sales")
    suspend fun createSale(@Body request: SaleRequest): OperationResult

    @POST("api/v1/cash-handovers")
    suspend fun handoverCash(@Body request: CashHandoverRequest): OperationResult
}

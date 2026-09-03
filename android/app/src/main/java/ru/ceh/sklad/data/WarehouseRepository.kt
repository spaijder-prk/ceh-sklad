package ru.ceh.sklad.data

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import ru.ceh.sklad.BuildConfig

class WarehouseRepository {
    private val api: WarehouseApi = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(WarehouseApi::class.java)

    suspend fun loadStocks(locationId: String? = null): List<StockItem> = api.getStocks(locationId)

    suspend fun createSale(request: SaleRequest): OperationResult = api.createSale(request)

    suspend fun handoverCash(request: CashHandoverRequest): OperationResult = api.handoverCash(request)
}

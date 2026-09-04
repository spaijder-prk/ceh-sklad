package ru.ceh.sklad.data

import retrofit2.http.Body
import retrofit2.http.Field
import retrofit2.http.FormUrlEncoded
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface CehApi {
    @FormUrlEncoded
    @POST("api/v1/auth/token")
    suspend fun login(
        @Field("username") email: String,
        @Field("password") password: String,
    ): TokenResponse

    @GET("api/v1/auth/me")
    suspend fun currentUser(): UserDto

    @GET("api/v1/warehouses")
    suspend fun warehouses(): List<WarehouseDto>

    @GET("api/v1/representatives")
    suspend fun representatives(): List<RepresentativeDto>

    @GET("api/v1/balances/warehouses")
    suspend fun warehouseBalances(): List<WarehouseBalanceDto>

    @GET("api/v1/balances/representatives")
    suspend fun representativeBalances(
        @Query("representative_id") representativeId: String? = null,
    ): List<RepresentativeBalanceDto>

    @GET("api/v1/representatives/{representative_id}/debt")
    suspend fun representativeDebt(
        @Path("representative_id") representativeId: String,
    ): RepresentativeDebtDto

    @POST("api/v1/operations/sale")
    suspend fun registerSale(@Body request: SaleRequestDto): OperationResultDto

    @POST("api/v1/operations/representative-return")
    suspend fun registerReturn(@Body request: ReturnRequestDto): OperationResultDto
}

package ru.ceh.sklad.data

import com.google.gson.annotations.SerializedName
import java.math.BigDecimal

data class TokenResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("token_type") val tokenType: String,
)

data class UserDto(
    val id: String,
    val email: String,
    @SerializedName("full_name") val fullName: String,
    val role: String,
)

data class WarehouseDto(
    val id: String,
    val code: String,
    val name: String,
)

data class RepresentativeDto(
    val id: String,
    val code: String,
    val name: String,
    @SerializedName("user_id") val userId: String?,
)

data class WarehouseBalanceDto(
    @SerializedName("warehouse_id") val warehouseId: String,
    @SerializedName("warehouse_code") val warehouseCode: String,
    @SerializedName("warehouse_name") val warehouseName: String,
    @SerializedName("product_id") val productId: String,
    val sku: String,
    @SerializedName("product_name") val productName: String,
    val unit: String,
    @SerializedName("retail_price") val retailPrice: BigDecimal,
    @SerializedName("wholesale_price") val wholesalePrice: BigDecimal,
    val quantity: BigDecimal,
)

data class RepresentativeBalanceDto(
    @SerializedName("representative_id") val representativeId: String,
    @SerializedName("representative_code") val representativeCode: String,
    @SerializedName("representative_name") val representativeName: String,
    @SerializedName("product_id") val productId: String,
    val sku: String,
    @SerializedName("product_name") val productName: String,
    val unit: String,
    @SerializedName("retail_price") val retailPrice: BigDecimal,
    @SerializedName("wholesale_price") val wholesalePrice: BigDecimal,
    val quantity: BigDecimal,
)

data class RepresentativeDebtDto(
    @SerializedName("representative_id") val representativeId: String,
    val debt: BigDecimal,
)

data class QuantityLineDto(
    @SerializedName("product_id") val productId: String,
    val quantity: BigDecimal,
)

data class SaleLineDto(
    @SerializedName("product_id") val productId: String,
    val quantity: BigDecimal,
    @SerializedName("price_type") val priceType: String,
)

data class SaleRequestDto(
    @SerializedName("representative_id") val representativeId: String,
    val lines: List<SaleLineDto>,
    val comment: String? = null,
    @SerializedName("external_id") val externalId: String? = null,
)

data class ReturnRequestDto(
    @SerializedName("representative_id") val representativeId: String,
    @SerializedName("warehouse_id") val warehouseId: String,
    val lines: List<QuantityLineDto>,
    val comment: String? = null,
    @SerializedName("external_id") val externalId: String? = null,
)

data class OperationResultDto(
    @SerializedName("document_id") val documentId: String?,
    @SerializedName("money_posting_id") val moneyPostingId: String?,
    @SerializedName("debt_delta") val debtDelta: BigDecimal,
)

data class DashboardData(
    val user: UserDto,
    val representative: RepresentativeDto?,
    val warehouses: List<WarehouseDto>,
    val warehouseBalances: List<WarehouseBalanceDto>,
    val representativeBalances: List<RepresentativeBalanceDto>,
    val debt: BigDecimal?,
)

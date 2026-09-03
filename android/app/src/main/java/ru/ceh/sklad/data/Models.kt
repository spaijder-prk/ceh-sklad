package ru.ceh.sklad.data

data class LoginRequest(val login: String, val password: String)
data class TokenResponse(val access_token: String, val token_type: String)
data class UserInfo(val id: String, val name: String, val login: String, val role: String, val location_id: String?)
data class LocationItem(val id: String, val name: String, val kind: String)

data class StockItem(
    val location_id: String,
    val location_name: String,
    val product_id: String,
    val sku: String,
    val product_name: String,
    val unit_name: String,
    val quantity: Double,
    val retail_price: Double,
    val wholesale_price: Double,
)

data class MovementItem(val product_id: String, val quantity: Double)

data class SaleRequest(
    val representative_location_id: String,
    val items: List<MovementItem>,
    val price_type: String,
    val comment: String? = null,
    val operation_key: String? = null,
)

data class TransferRequest(
    val source_location_id: String,
    val destination_location_id: String,
    val items: List<MovementItem>,
    val comment: String? = null,
    val operation_key: String? = null,
)

data class CashHandoverRequest(
    val representative_location_id: String,
    val amount: Double,
    val comment: String? = null,
    val operation_key: String? = null,
)

data class OperationResult(val id: String, val message: String)
data class DebtResponse(val representative_location_id: String, val debt: Double)

data class SubmissionResult(
    val confirmed: Boolean,
    val message: String,
    val operationKey: String,
)

data class PendingConflict(
    val operationKey: String,
    val message: String,
)

data class PendingSyncResult(
    val sent: Int,
    val pending: Int,
    val conflicts: List<PendingConflict>,
)

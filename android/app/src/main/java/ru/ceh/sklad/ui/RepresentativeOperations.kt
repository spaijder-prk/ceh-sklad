package ru.ceh.sklad.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import java.math.BigDecimal
import java.math.RoundingMode
import java.util.UUID
import ru.ceh.sklad.data.RepresentativeBalanceDto
import ru.ceh.sklad.data.WarehouseDto

@Composable
fun RepresentativeOperationsPanel(
    state: AppUiState,
    viewModel: AppViewModel = viewModel(),
) {
    if (state.user?.role != ROLE_REPRESENTATIVE) return

    var saleOpen by rememberSaveable { mutableStateOf(false) }
    var returnOpen by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(state.operationMessage) {
        if (state.operationMessage != null) {
            saleOpen = false
            returnOpen = false
        }
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("Операции", style = MaterialTheme.typography.titleMedium)
            Button(
                onClick = {
                    viewModel.clearOperationFeedback()
                    saleOpen = true
                },
                enabled = state.representativeBalances.isNotEmpty() && !state.operationLoading,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Продажа")
            }
            OutlinedButton(
                onClick = {
                    viewModel.clearOperationFeedback()
                    returnOpen = true
                },
                enabled = state.representativeBalances.isNotEmpty() &&
                    state.warehouses.isNotEmpty() &&
                    !state.operationLoading,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Возврат")
            }

            state.operationMessage?.let { message ->
                Text(message, color = MaterialTheme.colorScheme.primary)
            }
            state.operationError?.let { message ->
                Text(message, color = MaterialTheme.colorScheme.error)
            }
        }
    }

    if (saleOpen) {
        SaleDialog(
            products = state.representativeBalances,
            loading = state.operationLoading,
            error = state.operationError,
            onDismiss = { if (!state.operationLoading) saleOpen = false },
            onSubmit = { productId, quantity, priceType, externalId ->
                viewModel.registerSale(productId, quantity, priceType, externalId)
            },
        )
    }

    if (returnOpen) {
        ReturnDialog(
            products = state.representativeBalances,
            warehouses = state.warehouses,
            loading = state.operationLoading,
            error = state.operationError,
            onDismiss = { if (!state.operationLoading) returnOpen = false },
            onSubmit = { productId, quantity, warehouseId, externalId ->
                viewModel.registerReturn(productId, quantity, warehouseId, externalId)
            },
        )
    }
}

@Composable
private fun SaleDialog(
    products: List<RepresentativeBalanceDto>,
    loading: Boolean,
    error: String?,
    onDismiss: () -> Unit,
    onSubmit: (String, BigDecimal, String, String) -> Unit,
) {
    var selectedProductId by rememberSaveable { mutableStateOf(products.firstOrNull()?.productId.orEmpty()) }
    var quantityText by rememberSaveable { mutableStateOf("1") }
    var priceType by rememberSaveable { mutableStateOf(PRICE_RETAIL) }
    var externalId by rememberSaveable { mutableStateOf(newExternalId("sale")) }

    val selectedProduct = products.firstOrNull { it.productId == selectedProductId }
        ?: products.firstOrNull()
    val quantity = parseQuantity(quantityText)
    val validQuantity = quantity.isValidFor(selectedProduct)
    val unitPrice = selectedProduct?.let {
        if (priceType == PRICE_RETAIL) it.retailPrice else it.wholesalePrice
    }
    val amount = if (validQuantity && unitPrice != null && quantity != null) {
        quantity.multiply(unitPrice).setScale(2, RoundingMode.HALF_UP)
    } else {
        null
    }

    fun resetExternalId() {
        externalId = newExternalId("sale")
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Оформить продажу") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ProductSelector(
                    products = products,
                    selectedProductId = selectedProduct?.productId.orEmpty(),
                    onSelect = {
                        selectedProductId = it
                        resetExternalId()
                    },
                )

                selectedProduct?.let {
                    Text("Доступно: ${it.quantity.clean()} ${it.unit}")
                }

                QuantityField(
                    value = quantityText,
                    valid = validQuantity,
                    loading = loading,
                    onChange = {
                        quantityText = it
                        resetExternalId()
                    },
                )

                Text("Цена")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = priceType == PRICE_RETAIL,
                        onClick = {
                            priceType = PRICE_RETAIL
                            resetExternalId()
                        },
                        label = { Text("Розница") },
                        enabled = !loading,
                    )
                    FilterChip(
                        selected = priceType == PRICE_WHOLESALE,
                        onClick = {
                            priceType = PRICE_WHOLESALE
                            resetExternalId()
                        },
                        label = { Text("Опт") },
                        enabled = !loading,
                    )
                }

                unitPrice?.let { Text("Цена за единицу: ${it.money()} ₽") }
                amount?.let {
                    Text("Сумма: ${it.money()} ₽", style = MaterialTheme.typography.titleMedium)
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    if (selectedProduct != null && quantity != null) {
                        onSubmit(selectedProduct.productId, quantity, priceType, externalId)
                    }
                },
                enabled = validQuantity && !loading,
            ) {
                Text(if (loading) "Проводим…" else "Провести")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !loading) { Text("Отмена") }
        },
    )
}

@Composable
private fun ReturnDialog(
    products: List<RepresentativeBalanceDto>,
    warehouses: List<WarehouseDto>,
    loading: Boolean,
    error: String?,
    onDismiss: () -> Unit,
    onSubmit: (String, BigDecimal, String, String) -> Unit,
) {
    var selectedProductId by rememberSaveable { mutableStateOf(products.firstOrNull()?.productId.orEmpty()) }
    var selectedWarehouseId by rememberSaveable { mutableStateOf(warehouses.firstOrNull()?.id.orEmpty()) }
    var quantityText by rememberSaveable { mutableStateOf("1") }
    var externalId by rememberSaveable { mutableStateOf(newExternalId("return")) }

    val selectedProduct = products.firstOrNull { it.productId == selectedProductId }
        ?: products.firstOrNull()
    val selectedWarehouse = warehouses.firstOrNull { it.id == selectedWarehouseId }
        ?: warehouses.firstOrNull()
    val quantity = parseQuantity(quantityText)
    val validQuantity = quantity.isValidFor(selectedProduct)

    fun resetExternalId() {
        externalId = newExternalId("return")
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Вернуть товар на склад") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ProductSelector(
                    products = products,
                    selectedProductId = selectedProduct?.productId.orEmpty(),
                    onSelect = {
                        selectedProductId = it
                        resetExternalId()
                    },
                )

                selectedProduct?.let {
                    Text("Доступно: ${it.quantity.clean()} ${it.unit}")
                }

                WarehouseSelector(
                    warehouses = warehouses,
                    selectedWarehouseId = selectedWarehouse?.id.orEmpty(),
                    onSelect = {
                        selectedWarehouseId = it
                        resetExternalId()
                    },
                )

                QuantityField(
                    value = quantityText,
                    valid = validQuantity,
                    loading = loading,
                    onChange = {
                        quantityText = it
                        resetExternalId()
                    },
                )

                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    if (selectedProduct != null && selectedWarehouse != null && quantity != null) {
                        onSubmit(selectedProduct.productId, quantity, selectedWarehouse.id, externalId)
                    }
                },
                enabled = validQuantity && selectedWarehouse != null && !loading,
            ) {
                Text(if (loading) "Проводим…" else "Вернуть")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !loading) { Text("Отмена") }
        },
    )
}

@Composable
private fun QuantityField(
    value: String,
    valid: Boolean,
    loading: Boolean,
    onChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        modifier = Modifier.fillMaxWidth(),
        label = { Text("Количество") },
        supportingText = { Text("Не более 3 знаков после запятой") },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        enabled = !loading,
        isError = value.isNotBlank() && !valid,
    )
}

@Composable
private fun ProductSelector(
    products: List<RepresentativeBalanceDto>,
    selectedProductId: String,
    onSelect: (String) -> Unit,
) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    val selected = products.firstOrNull { it.productId == selectedProductId } ?: products.firstOrNull()

    Box(modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = { expanded = true },
            modifier = Modifier.fillMaxWidth(),
            enabled = products.isNotEmpty(),
        ) {
            Text(selected?.let { "${it.productName} · ${it.sku}" } ?: "Нет товара")
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            products.forEach { product ->
                DropdownMenuItem(
                    text = { Text("${product.productName} · ${product.quantity.clean()} ${product.unit}") },
                    onClick = {
                        onSelect(product.productId)
                        expanded = false
                    },
                )
            }
        }
    }
}

@Composable
private fun WarehouseSelector(
    warehouses: List<WarehouseDto>,
    selectedWarehouseId: String,
    onSelect: (String) -> Unit,
) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    val selected = warehouses.firstOrNull { it.id == selectedWarehouseId } ?: warehouses.firstOrNull()

    Box(modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = { expanded = true },
            modifier = Modifier.fillMaxWidth(),
            enabled = warehouses.isNotEmpty(),
        ) {
            Text(selected?.let { "${it.name} · ${it.code}" } ?: "Нет складов")
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            warehouses.forEach { warehouse ->
                DropdownMenuItem(
                    text = { Text("${warehouse.name} · ${warehouse.code}") },
                    onClick = {
                        onSelect(warehouse.id)
                        expanded = false
                    },
                )
            }
        }
    }
}

private fun newExternalId(kind: String): String = "android-$kind-${UUID.randomUUID()}"

private fun parseQuantity(value: String): BigDecimal? =
    value.trim().replace(',', '.').toBigDecimalOrNull()

private fun BigDecimal?.isValidFor(product: RepresentativeBalanceDto?): Boolean {
    if (this == null || product == null || this <= BigDecimal.ZERO || this > product.quantity) return false
    return stripTrailingZeros().scale() <= 3
}

private fun BigDecimal.clean(): String = stripTrailingZeros().toPlainString()

private fun BigDecimal.money(): String = setScale(2, RoundingMode.HALF_UP).toPlainString()

private const val ROLE_REPRESENTATIVE = "representative"
private const val PRICE_RETAIL = "retail"
private const val PRICE_WHOLESALE = "wholesale"

package ru.ceh.sklad.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import ru.ceh.sklad.data.CashHandoverRequest
import ru.ceh.sklad.data.LocationItem
import ru.ceh.sklad.data.MovementItem
import ru.ceh.sklad.data.SaleRequest
import ru.ceh.sklad.data.StockItem
import ru.ceh.sklad.data.TransferRequest
import ru.ceh.sklad.data.UserInfo
import ru.ceh.sklad.data.WarehouseRepository

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CehSkladApp() {
    MaterialTheme {
        val repository = remember { WarehouseRepository() }
        val scope = rememberCoroutineScope()
        var user by remember { mutableStateOf<UserInfo?>(null) }
        var login by remember { mutableStateOf("") }
        var password by remember { mutableStateOf("") }
        var stocks by remember { mutableStateOf<List<StockItem>>(emptyList()) }
        var locations by remember { mutableStateOf<List<LocationItem>>(emptyList()) }
        var debt by remember { mutableStateOf(0.0) }
        var loading by remember { mutableStateOf(false) }
        var error by remember { mutableStateOf<String?>(null) }
        var notice by remember { mutableStateOf<String?>(null) }
        var refreshKey by remember { mutableStateOf(0) }
        var screen by remember { mutableStateOf("warehouses") }

        suspend fun refresh() {
            val current = user ?: return
            loading = true
            error = null
            runCatching {
                stocks = repository.loadStocks()
                locations = repository.loadLocations()
                current.location_id?.let { debt = repository.loadDebt(it) }
            }.onFailure { error = it.message ?: "Не удалось получить данные" }
            loading = false
        }

        LaunchedEffect(user, refreshKey) {
            if (user != null) refresh()
        }

        DisposableEffect(user) {
            if (user == null) return@DisposableEffect onDispose { }
            val webSocket = repository.connectRealtime { scope.launch { refreshKey += 1 } }
            onDispose { webSocket?.close(1000, "Закрытие экрана") }
        }

        if (user == null) {
            LoginScreen(login, password, loading, error, { login = it }, { password = it }) {
                loading = true
                error = null
                scope.launch {
                    runCatching { repository.login(login.trim(), password) }
                        .onSuccess { user = it }
                        .onFailure { error = "Не удалось войти. Проверьте логин и пароль" }
                    loading = false
                }
            }
            return@MaterialTheme
        }

        val currentUser = user!!
        val ownStocks = currentUser.location_id?.let { ownId -> stocks.filter { it.location_id == ownId } }.orEmpty()
        val warehouseStocks = stocks.filter { item -> locations.firstOrNull { it.id == item.location_id }?.kind == "warehouse" }
        val warehouses = locations.filter { it.kind == "warehouse" }

        fun runOperation(block: suspend () -> String) {
            scope.launch {
                loading = true
                error = null
                notice = null
                runCatching { block() }
                    .onSuccess { notice = it; refreshKey += 1 }
                    .onFailure { error = it.message ?: "Операция не выполнена" }
                loading = false
            }
        }

        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text("Цех Склад") },
                    actions = {
                        TextButton(onClick = { refreshKey += 1 }) { Text("Обновить") }
                        TextButton(onClick = { repository.logout(); user = null; stocks = emptyList() }) { Text("Выйти") }
                    },
                )
            },
        ) { padding ->
            Column(modifier = Modifier.fillMaxSize().padding(padding).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("${currentUser.name} · долг: ${"%.2f".format(debt)}", style = MaterialTheme.typography.titleMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { screen = "warehouses" }) { Text("Склады") }
                    Button(onClick = { screen = "mine" }) { Text("Мой остаток") }
                    Button(onClick = { screen = "operations" }) { Text("Операции") }
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                notice?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
                if (loading) CircularProgressIndicator()
                when (screen) {
                    "mine" -> StockList("Мой остаток", ownStocks)
                    "operations" -> OperationsScreen(
                        ownStocks = ownStocks,
                        warehouses = warehouses,
                        representativeLocationId = currentUser.location_id,
                        onSale = { product, quantity, priceType ->
                            runOperation {
                                repository.createSale(SaleRequest(currentUser.location_id!!, listOf(MovementItem(product.product_id, quantity)), priceType)).message
                            }
                        },
                        onReturn = { product, quantity, warehouseId ->
                            runOperation {
                                repository.returnGoods(TransferRequest(currentUser.location_id!!, warehouseId, listOf(MovementItem(product.product_id, quantity)), "Возврат из Android-приложения")).message
                            }
                        },
                        onCash = { amount ->
                            runOperation { repository.handoverCash(CashHandoverRequest(currentUser.location_id!!, amount, "Сдача через Android-приложение")).message }
                        },
                    )
                    else -> StockList("Остатки на складах", warehouseStocks)
                }
            }
        }
    }
}

@Composable
private fun LoginScreen(login: String, password: String, loading: Boolean, error: String?, onLoginChanged: (String) -> Unit, onPasswordChanged: (String) -> Unit, onSubmit: () -> Unit) {
    Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
        Text("Цех Склад", style = MaterialTheme.typography.headlineLarge)
        Text("Вход торгового представителя", modifier = Modifier.padding(top = 4.dp, bottom = 20.dp))
        OutlinedTextField(login, onLoginChanged, label = { Text("Логин") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(password, onPasswordChanged, label = { Text("Пароль") }, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth().padding(top = 10.dp))
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 10.dp)) }
        Button(onClick = onSubmit, enabled = !loading && login.isNotBlank() && password.isNotBlank(), modifier = Modifier.padding(top = 16.dp)) { Text(if (loading) "Вход..." else "Войти") }
    }
}

@Composable
private fun StockList(title: String, rows: List<StockItem>) {
    Column(modifier = Modifier.fillMaxSize()) {
        Text(title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(bottom = 8.dp))
        if (rows.isEmpty()) Text("Нет данных")
        else LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) { items(rows, key = { "${it.location_id}:${it.product_id}" }) { StockCard(it) } }
    }
}

@Composable
private fun StockCard(item: StockItem) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(item.product_name, style = MaterialTheme.typography.titleMedium)
            Text("${item.location_name} · ${item.quantity} ${item.unit_name}")
            Text("Розница: ${item.retail_price} · Опт: ${item.wholesale_price}")
            Text("Артикул: ${item.sku}", style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun OperationsScreen(
    ownStocks: List<StockItem>,
    warehouses: List<LocationItem>,
    representativeLocationId: String?,
    onSale: (StockItem, Double, String) -> Unit,
    onReturn: (StockItem, Double, String) -> Unit,
    onCash: (Double) -> Unit,
) {
    var selectedProductId by remember { mutableStateOf<String?>(null) }
    var quantityText by remember { mutableStateOf("1") }
    var cashText by remember { mutableStateOf("") }
    var returnWarehouseId by remember { mutableStateOf<String?>(null) }
    val selected = ownStocks.firstOrNull { it.product_id == selectedProductId }
    val quantity = quantityText.replace(',', '.').toDoubleOrNull()

    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Text("Продажа и возврат", style = MaterialTheme.typography.titleLarge) }
        if (representativeLocationId == null) item { Text("К пользователю не привязан виртуальный склад") }
        items(ownStocks.filter { it.quantity > 0 }, key = { it.product_id }) { item ->
            Card(modifier = Modifier.fillMaxWidth().clickable { selectedProductId = item.product_id }) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(if (selectedProductId == item.product_id) "✓ ${item.product_name}" else item.product_name)
                    Text("Доступно ${item.quantity} ${item.unit_name}")
                }
            }
        }
        item {
            OutlinedTextField(value = quantityText, onValueChange = { quantityText = it }, label = { Text("Количество") }, modifier = Modifier.fillMaxWidth())
        }
        if (selected != null && quantity != null && quantity > 0) {
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { onSale(selected, quantity, "retail") }) { Text("Продать розница") }
                    Button(onClick = { onSale(selected, quantity, "wholesale") }) { Text("Продать опт") }
                }
            }
            item { Text("Возврат на склад", style = MaterialTheme.typography.titleMedium) }
            items(warehouses, key = { it.id }) { warehouse ->
                Button(onClick = { returnWarehouseId = warehouse.id }, modifier = Modifier.fillMaxWidth()) {
                    Text(if (returnWarehouseId == warehouse.id) "✓ ${warehouse.name}" else warehouse.name)
                }
            }
            if (returnWarehouseId != null) item { Button(onClick = { onReturn(selected, quantity, returnWarehouseId!!) }) { Text("Оформить возврат") } }
        }
        item { Text("Сдача денежных средств", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 12.dp)) }
        item { OutlinedTextField(value = cashText, onValueChange = { cashText = it }, label = { Text("Сумма") }, modifier = Modifier.fillMaxWidth()) }
        cashText.replace(',', '.').toDoubleOrNull()?.takeIf { it > 0 }?.let { amount -> item { Button(onClick = { onCash(amount); cashText = "" }) { Text("Сдать деньги") } } }
    }
}

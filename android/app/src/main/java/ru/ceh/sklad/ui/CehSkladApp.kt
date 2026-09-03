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
import androidx.compose.material3.AlertDialog
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import ru.ceh.sklad.data.CachedSnapshot
import ru.ceh.sklad.data.CashHandoverRequest
import ru.ceh.sklad.data.LocationItem
import ru.ceh.sklad.data.MovementItem
import ru.ceh.sklad.data.PendingConflict
import ru.ceh.sklad.data.RepresentativeHistory
import ru.ceh.sklad.data.SaleCartLine
import ru.ceh.sklad.data.SaleRequest
import ru.ceh.sklad.data.StockItem
import ru.ceh.sklad.data.SubmissionResult
import ru.ceh.sklad.data.TransferRequest
import ru.ceh.sklad.data.UserInfo
import ru.ceh.sklad.data.WarehouseRepository
import ru.ceh.sklad.data.addToSaleCart
import ru.ceh.sklad.data.saleCartTotal
import ru.ceh.sklad.data.saleUnitPrice
import java.text.DateFormat
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Date

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CehSkladApp() {
    MaterialTheme {
        val context = LocalContext.current
        val repository = remember { WarehouseRepository(context.applicationContext) }
        val scope = rememberCoroutineScope()
        var user by remember { mutableStateOf<UserInfo?>(null) }
        var login by remember { mutableStateOf("") }
        var password by remember { mutableStateOf("") }
        var stocks by remember { mutableStateOf<List<StockItem>>(emptyList()) }
        var locations by remember { mutableStateOf<List<LocationItem>>(emptyList()) }
        var debt by remember { mutableStateOf(0.0) }
        var history by remember { mutableStateOf(RepresentativeHistory()) }
        var historyLoading by remember { mutableStateOf(false) }
        var lastSyncAt by remember { mutableStateOf<Long?>(null) }
        var pendingCount by remember { mutableStateOf(0) }
        var pendingConflicts by remember { mutableStateOf<List<PendingConflict>>(emptyList()) }
        var restoring by remember { mutableStateOf(true) }
        var loading by remember { mutableStateOf(false) }
        var error by remember { mutableStateOf<String?>(null) }
        var notice by remember { mutableStateOf<String?>(null) }
        var refreshKey by remember { mutableStateOf(0) }
        var screen by remember { mutableStateOf("warehouses") }

        fun applySnapshot(snapshot: CachedSnapshot) {
            stocks = snapshot.stocks
            locations = snapshot.locations
            debt = snapshot.debt
            lastSyncAt = snapshot.syncedAt
        }

        suspend fun refresh() {
            val current = user ?: return
            loading = true
            error = null
            try {
                val sync = repository.syncPendingOperations()
                pendingCount = sync.pending
                pendingConflicts = sync.conflicts
                if (sync.sent > 0) notice = "Отправлено из очереди и подтверждено сервером: ${sync.sent}"
                applySnapshot(repository.loadSnapshot(current.location_id))
            } catch (failure: Exception) {
                pendingCount = repository.pendingCount()
                val cached = repository.cachedSnapshot()
                if (cached != null) {
                    applySnapshot(cached)
                    error = "Нет связи с сервером. Показаны последние подтвержденные данные."
                } else {
                    error = failure.message ?: "Не удалось получить данные"
                }
            } finally {
                loading = false
            }
        }

        LaunchedEffect(Unit) {
            user = repository.restoreSession()
            pendingCount = repository.pendingCount()
            restoring = false
        }

        LaunchedEffect(user, refreshKey) {
            if (user != null) refresh()
        }

        LaunchedEffect(user, screen, refreshKey) {
            if (user != null && screen == "history") {
                historyLoading = true
                runCatching { repository.loadHistory() }
                    .onSuccess { history = it }
                    .onFailure { error = it.message ?: "Не удалось получить историю операций" }
                historyLoading = false
            }
        }

        DisposableEffect(user) {
            if (user == null) return@DisposableEffect onDispose { }
            val subscription = repository.connectRealtime { scope.launch { refreshKey += 1 } }
            onDispose { subscription?.close() }
        }

        if (restoring) {
            Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
                CircularProgressIndicator()
                Text("Восстановление сессии…", modifier = Modifier.padding(top = 12.dp))
            }
            return@MaterialTheme
        }

        if (user == null) {
            LoginScreen(login, password, loading, error, { login = it }, { password = it }) {
                loading = true
                error = null
                scope.launch {
                    runCatching { repository.login(login.trim(), password) }
                        .onSuccess {
                            user = it
                            password = ""
                            pendingCount = repository.pendingCount()
                        }
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

        fun runOperation(block: suspend () -> SubmissionResult) {
            if (loading) return
            scope.launch {
                loading = true
                error = null
                notice = null
                val result = runCatching { block() }
                result.onSuccess { submission ->
                    notice = submission.message
                    if (submission.confirmed) refreshKey += 1
                }.onFailure {
                    error = it.message ?: "Операция не выполнена"
                }
                pendingCount = repository.pendingCount()
                loading = false
            }
        }

        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text("Цех Склад") },
                    actions = {
                        TextButton(onClick = { refreshKey += 1 }) { Text("Обновить") }
                        TextButton(onClick = {
                            scope.launch {
                                repository.logout()
                                user = null
                                stocks = emptyList()
                                locations = emptyList()
                                history = RepresentativeHistory()
                                debt = 0.0
                                lastSyncAt = null
                                pendingCount = 0
                                pendingConflicts = emptyList()
                            }
                        }) { Text("Выйти") }
                    },
                )
            },
        ) { padding ->
            Column(modifier = Modifier.fillMaxSize().padding(padding).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("${currentUser.name} · долг: ${"%.2f".format(debt)}", style = MaterialTheme.typography.titleMedium)
                lastSyncAt?.let {
                    Text("Данные на ${DateFormat.getDateTimeInstance().format(Date(it))}", style = MaterialTheme.typography.bodySmall)
                }
                if (pendingCount > 0) {
                    Text("Ожидают подтверждения сервера: $pendingCount", color = MaterialTheme.colorScheme.tertiary)
                }
                pendingConflicts.forEach { conflict ->
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Конфликт очереди", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.error)
                            Text(conflict.message, style = MaterialTheme.typography.bodySmall)
                            TextButton(onClick = {
                                scope.launch {
                                    repository.discardPending(conflict.operationKey)
                                    pendingConflicts = pendingConflicts.filterNot { it.operationKey == conflict.operationKey }
                                    pendingCount = repository.pendingCount()
                                }
                            }) { Text("Удалить неподтвержденную операцию") }
                        }
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { screen = "warehouses" }) { Text("Склады") }
                    Button(onClick = { screen = "mine" }) { Text("Мой остаток") }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { screen = "operations" }) { Text("Операции") }
                    Button(onClick = { screen = "history" }) { Text("История") }
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                notice?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
                if (loading || historyLoading) CircularProgressIndicator()
                when (screen) {
                    "mine" -> StockList("Мой остаток", ownStocks)
                    "operations" -> OperationsScreen(
                        ownStocks = ownStocks,
                        warehouses = warehouses,
                        representativeLocationId = currentUser.location_id,
                        operationsEnabled = !loading,
                        onSale = { items, priceType ->
                            runOperation {
                                repository.createSale(SaleRequest(currentUser.location_id!!, items, priceType, "Продажа через Android-приложение"))
                            }
                        },
                        onReturn = { product, quantity, warehouseId ->
                            runOperation {
                                repository.returnGoods(TransferRequest(currentUser.location_id!!, warehouseId, listOf(MovementItem(product.product_id, quantity)), "Возврат из Android-приложения"))
                            }
                        },
                        onCash = { amount ->
                            runOperation { repository.handoverCash(CashHandoverRequest(currentUser.location_id!!, amount, "Сдача через Android-приложение")) }
                        },
                    )
                    "history" -> HistoryScreen(history)
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
    operationsEnabled: Boolean,
    onSale: (List<MovementItem>, String) -> Unit,
    onReturn: (StockItem, Double, String) -> Unit,
    onCash: (Double) -> Unit,
) {
    var saleProductId by remember { mutableStateOf<String?>(null) }
    var saleQuantityText by remember { mutableStateOf("1") }
    var salePriceType by remember { mutableStateOf("retail") }
    var cart by remember { mutableStateOf<List<SaleCartLine>>(emptyList()) }
    var confirmSale by remember { mutableStateOf(false) }
    var localError by remember { mutableStateOf<String?>(null) }

    var returnProductId by remember { mutableStateOf<String?>(null) }
    var returnQuantityText by remember { mutableStateOf("1") }
    var returnWarehouseId by remember { mutableStateOf<String?>(null) }
    var cashText by remember { mutableStateOf("") }

    val saleProduct = ownStocks.firstOrNull { it.product_id == saleProductId }
    val saleQuantity = saleQuantityText.replace(',', '.').toDoubleOrNull()
    val returnProduct = ownStocks.firstOrNull { it.product_id == returnProductId }
    val returnQuantity = returnQuantityText.replace(',', '.').toDoubleOrNull()

    if (confirmSale && cart.isNotEmpty()) {
        AlertDialog(
            onDismissRequest = { confirmSale = false },
            title = { Text("Подтвердить продажу") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    cart.forEach { line ->
                        Text("${line.product.product_name}: ${line.quantity} ${line.product.unit_name} × ${"%.2f".format(saleUnitPrice(line.product, salePriceType))}")
                    }
                    Text("Итого: ${"%.2f".format(saleCartTotal(cart, salePriceType))}", style = MaterialTheme.typography.titleMedium)
                    Text(if (salePriceType == "wholesale") "Тип цены: оптовая" else "Тип цены: розничная")
                }
            },
            confirmButton = {
                Button(enabled = operationsEnabled, onClick = {
                    val items = cart.map { MovementItem(it.product.product_id, it.quantity) }
                    onSale(items, salePriceType)
                    cart = emptyList()
                    confirmSale = false
                }) { Text("Провести") }
            },
            dismissButton = { TextButton(onClick = { confirmSale = false }) { Text("Отмена") } },
        )
    }

    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Text("Продажа", style = MaterialTheme.typography.titleLarge) }
        if (representativeLocationId == null) item { Text("К пользователю не привязан виртуальный склад") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { salePriceType = "retail" }) { Text(if (salePriceType == "retail") "✓ Розница" else "Розница") }
                Button(onClick = { salePriceType = "wholesale" }) { Text(if (salePriceType == "wholesale") "✓ Опт" else "Опт") }
            }
        }
        items(ownStocks.filter { it.quantity > 0 }, key = { "sale-${it.product_id}" }) { item ->
            Card(modifier = Modifier.fillMaxWidth().clickable { saleProductId = item.product_id; localError = null }) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(if (saleProductId == item.product_id) "✓ ${item.product_name}" else item.product_name)
                    Text("Доступно ${item.quantity} ${item.unit_name} · цена ${"%.2f".format(saleUnitPrice(item, salePriceType))}")
                }
            }
        }
        item { OutlinedTextField(value = saleQuantityText, onValueChange = { saleQuantityText = it }, label = { Text("Количество в корзину") }, modifier = Modifier.fillMaxWidth()) }
        if (saleProduct != null && saleQuantity != null && saleQuantity > 0) {
            item {
                Button(onClick = {
                    runCatching { addToSaleCart(cart, saleProduct, saleQuantity) }
                        .onSuccess { cart = it; localError = null }
                        .onFailure { localError = it.message }
                }) { Text("Добавить в корзину") }
            }
        }
        localError?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
        if (cart.isNotEmpty()) {
            item { Text("Корзина", style = MaterialTheme.typography.titleMedium) }
            items(cart, key = { "cart-${it.product.product_id}" }) { line ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Row(modifier = Modifier.fillMaxWidth().padding(10.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(line.product.product_name)
                            Text("${line.quantity} ${line.product.unit_name} · ${"%.2f".format(line.quantity * saleUnitPrice(line.product, salePriceType))}")
                        }
                        TextButton(onClick = { cart = cart.filterNot { it.product.product_id == line.product.product_id } }) { Text("Убрать") }
                    }
                }
            }
            item { Text("Итого: ${"%.2f".format(saleCartTotal(cart, salePriceType))}", style = MaterialTheme.typography.titleLarge) }
            item { Button(enabled = operationsEnabled, onClick = { confirmSale = true }) { Text("Подтвердить продажу") } }
        }

        item { Text("Возврат на склад", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 12.dp)) }
        items(ownStocks.filter { it.quantity > 0 }, key = { "return-${it.product_id}" }) { item ->
            Card(modifier = Modifier.fillMaxWidth().clickable { returnProductId = item.product_id }) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(if (returnProductId == item.product_id) "✓ ${item.product_name}" else item.product_name)
                    Text("Доступно ${item.quantity} ${item.unit_name}")
                }
            }
        }
        item { OutlinedTextField(value = returnQuantityText, onValueChange = { returnQuantityText = it }, label = { Text("Количество возврата") }, modifier = Modifier.fillMaxWidth()) }
        if (returnProduct != null && returnQuantity != null && returnQuantity > 0) {
            items(warehouses, key = { "warehouse-${it.id}" }) { warehouse ->
                Button(onClick = { returnWarehouseId = warehouse.id }, modifier = Modifier.fillMaxWidth()) {
                    Text(if (returnWarehouseId == warehouse.id) "✓ ${warehouse.name}" else warehouse.name)
                }
            }
            if (returnWarehouseId != null) {
                item {
                    Button(enabled = operationsEnabled && returnQuantity <= returnProduct.quantity, onClick = {
                        onReturn(returnProduct, returnQuantity, returnWarehouseId!!)
                    }) { Text("Оформить возврат") }
                }
            }
        }

        item { Text("Сдача денежных средств", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 12.dp)) }
        item { OutlinedTextField(value = cashText, onValueChange = { cashText = it }, label = { Text("Сумма") }, modifier = Modifier.fillMaxWidth()) }
        cashText.replace(',', '.').toDoubleOrNull()?.takeIf { it > 0 }?.let { amount ->
            item {
                Button(enabled = operationsEnabled, onClick = { onCash(amount); cashText = "" }) { Text("Сдать деньги") }
            }
        }
    }
}

@Composable
private fun HistoryScreen(history: RepresentativeHistory) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item { Text("Моя история операций", style = MaterialTheme.typography.titleLarge) }
        item { Text("Товар", style = MaterialTheme.typography.titleMedium) }
        if (history.stock.isEmpty()) item { Text("Складских операций пока нет") }
        items(history.stock, key = { "stock-${it.id}" }) { operation ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(stockKindLabel(operation.kind), style = MaterialTheme.typography.titleSmall)
                    Text(formatApiDate(operation.created_at), style = MaterialTheme.typography.bodySmall)
                    operation.lines.forEach { line ->
                        Text("${line.product_name}: ${line.quantity} ${line.unit_name}${line.unit_price?.let { " × ${"%.2f".format(it)}" } ?: ""}")
                    }
                    operation.destination_location_name?.let { Text("Куда: $it") }
                    operation.comment?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
        item { Text("Деньги", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 8.dp)) }
        if (history.money.isEmpty()) item { Text("Денежных операций пока нет") }
        items(history.money, key = { "money-${it.id}" }) { operation ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(moneyKindLabel(operation.kind), style = MaterialTheme.typography.titleSmall)
                    Text(formatApiDate(operation.created_at), style = MaterialTheme.typography.bodySmall)
                    val shownAmount = if (operation.kind == "cash_handover") -operation.amount else operation.amount
                    Text("Сумма: ${"%.2f".format(shownAmount)}")
                    operation.comment?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
    }
}

private fun stockKindLabel(kind: String): String = when (kind) {
    "sale" -> "Продажа"
    "representative_return" -> "Возврат"
    "issue_to_representative" -> "Получение товара"
    "transfer" -> "Перемещение"
    "adjustment" -> "Корректировка"
    else -> kind
}

private fun moneyKindLabel(kind: String): String = when (kind) {
    "sale" -> "Выручка от продажи"
    "cash_handover" -> "Сдача денежных средств"
    "adjustment" -> "Корректировка денег"
    else -> kind
}

private fun formatApiDate(value: String): String = runCatching {
    val time = OffsetDateTime.parse(value).atZoneSameInstant(ZoneId.systemDefault())
    time.format(DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm"))
}.getOrElse { value.replace('T', ' ').take(16) }

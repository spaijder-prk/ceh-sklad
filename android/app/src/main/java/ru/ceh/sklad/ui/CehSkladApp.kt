package ru.ceh.sklad.ui

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
import ru.ceh.sklad.data.StockItem
import ru.ceh.sklad.data.WarehouseRepository

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CehSkladApp() {
    MaterialTheme {
        val repository = remember { WarehouseRepository() }
        val scope = rememberCoroutineScope()
        var authorized by remember { mutableStateOf(false) }
        var login by remember { mutableStateOf("") }
        var password by remember { mutableStateOf("") }
        var stocks by remember { mutableStateOf<List<StockItem>>(emptyList()) }
        var loading by remember { mutableStateOf(false) }
        var error by remember { mutableStateOf<String?>(null) }
        var refreshKey by remember { mutableStateOf(0) }

        LaunchedEffect(authorized, refreshKey) {
            if (!authorized) return@LaunchedEffect
            loading = true
            error = null
            runCatching { repository.loadStocks() }
                .onSuccess { stocks = it }
                .onFailure { error = it.message ?: "Не удалось получить остатки" }
            loading = false
        }

        DisposableEffect(authorized) {
            if (!authorized) return@DisposableEffect onDispose { }
            val webSocket = repository.connectRealtime {
                scope.launch { refreshKey += 1 }
            }
            onDispose { webSocket?.close(1000, "Закрытие экрана") }
        }

        if (!authorized) {
            LoginScreen(
                login = login,
                password = password,
                loading = loading,
                error = error,
                onLoginChanged = { login = it },
                onPasswordChanged = { password = it },
                onSubmit = {
                    loading = true
                    error = null
                    scope.launch {
                        runCatching { repository.login(login.trim(), password) }
                            .onSuccess { authorized = true }
                            .onFailure { error = "Не удалось войти. Проверьте логин и пароль" }
                        loading = false
                    }
                },
            )
            return@MaterialTheme
        }

        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text("Цех Склад") },
                    actions = {
                        TextButton(onClick = {
                            repository.logout()
                            authorized = false
                            stocks = emptyList()
                        }) { Text("Выйти") }
                    },
                )
            },
        ) { padding ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("Остатки по складам", style = MaterialTheme.typography.titleLarge)
                    Button(onClick = { refreshKey += 1 }) { Text("Обновить") }
                }
                when {
                    loading -> CircularProgressIndicator()
                    error != null -> Text(error!!, color = MaterialTheme.colorScheme.error)
                    stocks.isEmpty() -> Text("Нет данных об остатках")
                    else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        items(stocks, key = { "${it.location_id}:${it.product_id}" }) { item -> StockCard(item) }
                    }
                }
            }
        }
    }
}

@Composable
private fun LoginScreen(
    login: String,
    password: String,
    loading: Boolean,
    error: String?,
    onLoginChanged: (String) -> Unit,
    onPasswordChanged: (String) -> Unit,
    onSubmit: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Цех Склад", style = MaterialTheme.typography.headlineLarge)
        Text("Вход в рабочее приложение", modifier = Modifier.padding(top = 4.dp, bottom = 20.dp))
        OutlinedTextField(login, onLoginChanged, label = { Text("Логин") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(
            password,
            onPasswordChanged,
            label = { Text("Пароль") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        )
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 10.dp)) }
        Button(onClick = onSubmit, enabled = !loading && login.isNotBlank() && password.isNotBlank(), modifier = Modifier.padding(top = 16.dp)) {
            Text(if (loading) "Вход..." else "Войти")
        }
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

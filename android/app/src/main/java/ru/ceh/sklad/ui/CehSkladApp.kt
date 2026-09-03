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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import ru.ceh.sklad.data.StockItem
import ru.ceh.sklad.data.WarehouseRepository

@Composable
fun CehSkladApp() {
    MaterialTheme {
        val repository = remember { WarehouseRepository() }
        var stocks by remember { mutableStateOf<List<StockItem>>(emptyList()) }
        var loading by remember { mutableStateOf(true) }
        var error by remember { mutableStateOf<String?>(null) }
        var refreshKey by remember { mutableStateOf(0) }

        LaunchedEffect(refreshKey) {
            loading = true
            error = null
            runCatching { repository.loadStocks() }
                .onSuccess { stocks = it }
                .onFailure { error = it.message ?: "Не удалось получить остатки" }
            loading = false
        }

        Scaffold(
            topBar = { TopAppBar(title = { Text("Цех Склад") }) },
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
                        items(stocks, key = { "${it.location_id}:${it.product_id}" }) { item ->
                            StockCard(item)
                        }
                    }
                }
            }
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

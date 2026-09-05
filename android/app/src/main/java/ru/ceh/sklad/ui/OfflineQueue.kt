package ru.ceh.sklad.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import ru.ceh.sklad.data.offline.PendingOperationEntity
import ru.ceh.sklad.data.offline.PendingOperationSummary

@Composable
fun OfflineQueueSection(
    state: AppUiState,
    onRetry: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Офлайн-очередь", style = MaterialTheme.typography.titleLarge)
        Text(
            "Сохраненные операции текущего торгового представителя",
            style = MaterialTheme.typography.bodySmall,
        )
        state.offlineOperations.forEach { operation ->
            OfflineOperationCard(
                operation = operation,
                state = state,
                onRetry = onRetry,
            )
        }
    }
}

@Composable
private fun OfflineOperationCard(
    operation: PendingOperationSummary,
    state: AppUiState,
    onRetry: (String) -> Unit,
) {
    val ownBalance = state.representativeBalances.firstOrNull {
        it.productId == operation.productId
    }
    val warehouseBalance = state.warehouseBalances.firstOrNull {
        it.productId == operation.productId
    }
    val productName = ownBalance?.productName ?: warehouseBalance?.productName
        ?: "Товар ${operation.productId.take(8)}"
    val sku = ownBalance?.sku ?: warehouseBalance?.sku.orEmpty()
    val unit = ownBalance?.unit ?: warehouseBalance?.unit.orEmpty()
    val destination = operation.warehouseId?.let { warehouseId ->
        state.warehouses.firstOrNull { it.id == warehouseId }?.name
            ?: "склад ${warehouseId.take(8)}"
    }
    val failed = operation.status == PendingOperationEntity.STATUS_FAILED

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            Row(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(operation.typeTitle(), style = MaterialTheme.typography.titleMedium)
                    Text(
                        operation.createdAt.readableDateTime(),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                Text(
                    text = if (failed) "Требует проверки" else "Ожидает отправки",
                    color = if (failed) {
                        MaterialTheme.colorScheme.error
                    } else {
                        MaterialTheme.colorScheme.primary
                    },
                    style = MaterialTheme.typography.labelMedium,
                )
            }

            Text(if (sku.isBlank()) productName else "$productName · $sku")
            Text(
                "Количество: ${operation.quantity.stripTrailingZeros().toPlainString()}" +
                    if (unit.isBlank()) "" else " $unit",
            )

            when (operation.operationType) {
                PendingOperationEntity.TYPE_SALE -> Text(
                    "Цена: ${if (operation.priceType == "wholesale") "оптовая" else "розничная"}",
                    style = MaterialTheme.typography.bodySmall,
                )
                PendingOperationEntity.TYPE_RETURN -> Text(
                    "Возврат на: ${destination ?: "склад не определен"}",
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            if (operation.attempts > 0) {
                Text(
                    "Попыток отправки: ${operation.attempts}",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            operation.lastError?.takeIf { it.isNotBlank() }?.let { message ->
                Text(
                    "Последняя ошибка: $message",
                    color = if (failed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (failed) {
                OutlinedButton(onClick = { onRetry(operation.externalId) }) {
                    Text("Повторить эту операцию")
                }
            }
        }
    }
}

private fun PendingOperationSummary.typeTitle(): String = when (operationType) {
    PendingOperationEntity.TYPE_SALE -> "Продажа"
    PendingOperationEntity.TYPE_RETURN -> "Возврат"
    else -> "Операция"
}

private fun Long.readableDateTime(): String = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm")
    .withZone(ZoneId.systemDefault())
    .format(Instant.ofEpochMilli(this))

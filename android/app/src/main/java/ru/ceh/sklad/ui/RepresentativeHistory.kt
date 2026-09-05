package ru.ceh.sklad.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import java.math.BigDecimal
import java.math.RoundingMode
import ru.ceh.sklad.data.DocumentDto

@Composable
fun RepresentativeHistoryCard(document: DocumentDto) {
    val representativeLines = document.lines.filter { it.representativeId != null }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(documentTypeTitle(document.documentType), style = MaterialTheme.typography.titleMedium)
                    Text(
                        text = document.postedAt.toReadableDateTime(),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                Text(
                    text = if (document.status == "cancelled") "Сторнирован" else "Проведен",
                    style = MaterialTheme.typography.labelMedium,
                    color = if (document.status == "cancelled") {
                        MaterialTheme.colorScheme.error
                    } else {
                        MaterialTheme.colorScheme.primary
                    },
                )
            }

            Spacer(Modifier.height(8.dp))
            representativeLines.forEach { line ->
                val direction = when {
                    line.quantity > BigDecimal.ZERO -> "+"
                    line.quantity < BigDecimal.ZERO -> "−"
                    else -> ""
                }
                Text(
                    text = "${line.productName} · ${line.sku}: $direction${line.quantity.abs().clean()}",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }

            if (document.documentType == "sale" && document.saleAmount != BigDecimal.ZERO) {
                Spacer(Modifier.height(6.dp))
                Text(
                    text = "Сумма продажи: ${document.saleAmount.money()} ₽",
                    style = MaterialTheme.typography.bodyLarge,
                )
            }

            document.comment?.takeIf { it.isNotBlank() }?.let { comment ->
                Spacer(Modifier.height(4.dp))
                Text(comment, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

private fun documentTypeTitle(type: String): String = when (type) {
    "issue_to_representative" -> "Получение товара"
    "representative_return" -> "Возврат на склад"
    "sale" -> "Продажа"
    "adjustment" -> "Корректировка"
    else -> "Операция"
}

private fun String.toReadableDateTime(): String =
    replace('T', ' ').take(16)

private fun BigDecimal.clean(): String = stripTrailingZeros().toPlainString()

private fun BigDecimal.money(): String = setScale(2, RoundingMode.HALF_UP).toPlainString()

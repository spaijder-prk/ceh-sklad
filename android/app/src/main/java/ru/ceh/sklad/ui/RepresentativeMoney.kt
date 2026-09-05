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
import ru.ceh.sklad.data.MoneyPostingDto

@Composable
fun RepresentativeMoneyCard(posting: MoneyPostingDto) {
    val presentation = posting.presentation()
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(presentation.title, style = MaterialTheme.typography.titleMedium)
                    Text(
                        posting.createdAt.toReadableDateTime(),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                if (posting.reversed) {
                    Text(
                        "Сторнирована",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
            }
            Spacer(Modifier.height(6.dp))
            Text(
                presentation.amountText,
                style = MaterialTheme.typography.bodyLarge,
                color = presentation.amountColor(),
            )
            posting.comment?.takeIf { it.isNotBlank() }?.let { comment ->
                Spacer(Modifier.height(4.dp))
                Text(comment, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

private data class MoneyPresentation(
    val title: String,
    val amountText: String,
    val debtIncreases: Boolean,
)

@Composable
private fun MoneyPresentation.amountColor() = if (debtIncreases) {
    MaterialTheme.colorScheme.error
} else {
    MaterialTheme.colorScheme.primary
}

private fun MoneyPostingDto.presentation(): MoneyPresentation = when (operation) {
    "sale" -> MoneyPresentation(
        title = "Продажа",
        amountText = "Задолженность +${amount.abs().money()} ₽",
        debtIncreases = true,
    )
    "payment" -> MoneyPresentation(
        title = "Сдача денег",
        amountText = "Задолженность −${amount.abs().money()} ₽",
        debtIncreases = false,
    )
    "adjustment" -> if (amount >= BigDecimal.ZERO) {
        MoneyPresentation(
            title = "Корректировка",
            amountText = "Задолженность +${amount.abs().money()} ₽",
            debtIncreases = true,
        )
    } else {
        MoneyPresentation(
            title = "Корректировка",
            amountText = "Задолженность −${amount.abs().money()} ₽",
            debtIncreases = false,
        )
    }
    else -> MoneyPresentation(
        title = "Денежная операция",
        amountText = "Изменение: ${amount.money()} ₽",
        debtIncreases = amount > BigDecimal.ZERO,
    )
}

private fun String.toReadableDateTime(): String = replace('T', ' ').take(16)

private fun BigDecimal.money(): String = setScale(2, RoundingMode.HALF_UP).toPlainString()

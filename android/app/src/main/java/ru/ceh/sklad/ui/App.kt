package ru.ceh.sklad.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import java.math.BigDecimal
import java.math.RoundingMode

@Composable
fun CehApp(viewModel: AppViewModel = viewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    MaterialTheme {
        if (state.user == null) {
            LoginScreen(
                state = state,
                onEmailChanged = viewModel::setEmail,
                onPasswordChanged = viewModel::setPassword,
                onLogin = viewModel::login,
            )
        } else {
            DashboardScreen(
                state = state,
                onRefresh = { viewModel.refresh() },
                onRetryFailed = viewModel::retryFailedOperations,
                onLogout = viewModel::logout,
            )
        }
    }
}

@Composable
private fun LoginScreen(
    state: AppUiState,
    onEmailChanged: (String) -> Unit,
    onPasswordChanged: (String) -> Unit,
    onLogin: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = "Цех — склад",
            style = MaterialTheme.typography.headlineLarge,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = "Вход торгового представителя",
            style = MaterialTheme.typography.bodyLarge,
        )
        Spacer(Modifier.height(24.dp))

        OutlinedTextField(
            value = state.email,
            onValueChange = onEmailChanged,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Email") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            enabled = !state.loading,
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = state.password,
            onValueChange = onPasswordChanged,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Пароль") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            enabled = !state.loading,
        )

        state.error?.let {
            Spacer(Modifier.height(12.dp))
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
            )
        }

        Spacer(Modifier.height(20.dp))
        Button(
            onClick = onLogin,
            enabled = !state.loading,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.loading) {
                CircularProgressIndicator(
                    modifier = Modifier.height(20.dp),
                    strokeWidth = 2.dp,
                )
            } else {
                Text("Войти")
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DashboardScreen(
    state: AppUiState,
    onRefresh: () -> Unit,
    onRetryFailed: () -> Unit,
    onLogout: () -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(state.user?.fullName.orEmpty())
                        Text(
                            text = if (state.realtimeActive) "Обновления: онлайн" else "Обновления: вручную",
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                },
                actions = {
                    TextButton(onClick = onLogout) {
                        Text("Выйти")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("Остатки на складах", style = MaterialTheme.typography.titleLarge)
                    OutlinedButton(onClick = onRefresh) {
                        Text("Обновить")
                    }
                }
            }

            state.error?.let { message ->
                item {
                    Text(message, color = MaterialTheme.colorScheme.error)
                }
            }

            if (state.warehouseBalances.isEmpty()) {
                item { EmptyCard("На складах пока нет остатков") }
            } else {
                items(
                    items = state.warehouseBalances,
                    key = { "${it.warehouseId}:${it.productId}" },
                ) { line ->
                    BalanceCard(
                        title = line.productName,
                        subtitle = "${line.warehouseName} · ${line.sku}",
                        quantity = "${line.quantity.clean()} ${line.unit}",
                        retailPrice = line.retailPrice,
                        wholesalePrice = line.wholesalePrice,
                    )
                }
            }

            item {
                Spacer(Modifier.height(8.dp))
                Text("Мой товар", style = MaterialTheme.typography.titleLarge)
            }

            if (state.user?.role != "representative") {
                item { EmptyCard("Этот раздел доступен учетной записи торгового представителя") }
            } else if (state.representativeBalances.isEmpty()) {
                item { EmptyCard("За представителем сейчас нет товара") }
            } else {
                items(
                    items = state.representativeBalances,
                    key = { it.productId },
                ) { line ->
                    BalanceCard(
                        title = line.productName,
                        subtitle = line.sku,
                        quantity = "${line.quantity.clean()} ${line.unit}",
                        retailPrice = line.retailPrice,
                        wholesalePrice = line.wholesalePrice,
                    )
                }
            }

            if (state.user?.role == "representative") {
                item {
                    RepresentativeOperationsPanel(state = state)
                }
                if (state.pendingOperations > 0 || state.failedOperations > 0) {
                    item {
                        OfflineQueueCard(
                            pending = state.pendingOperations,
                            failed = state.failedOperations,
                            onRetryFailed = onRetryFailed,
                        )
                    }
                }
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(16.dp)) {
                            Text("Задолженность", style = MaterialTheme.typography.titleMedium)
                            Spacer(Modifier.height(4.dp))
                            Text(
                                text = "${(state.debt ?: BigDecimal.ZERO).money()} ₽",
                                style = MaterialTheme.typography.headlineSmall,
                            )
                        }
                    }
                }
                item {
                    Spacer(Modifier.height(8.dp))
                    Text("Деньги и расчеты", style = MaterialTheme.typography.titleLarge)
                    Text(
                        "Продажи, подтвержденные сдачи денег и корректировки",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                if (state.moneyPostings.isEmpty()) {
                    item { EmptyCard("Денежных операций пока нет") }
                } else {
                    items(
                        items = state.moneyPostings,
                        key = { "money:${it.id}" },
                    ) { posting ->
                        RepresentativeMoneyCard(posting)
                    }
                }
                item {
                    Spacer(Modifier.height(8.dp))
                    Text("История операций", style = MaterialTheme.typography.titleLarge)
                    Text(
                        "Последние операции по вашему товару",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                if (state.documents.isEmpty()) {
                    item { EmptyCard("Операций пока нет") }
                } else {
                    items(
                        items = state.documents,
                        key = { "document:${it.id}" },
                    ) { document ->
                        RepresentativeHistoryCard(document)
                    }
                }
            }
        }
    }
}

@Composable
private fun OfflineQueueCard(
    pending: Int,
    failed: Int,
    onRetryFailed: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text("Офлайн-очередь", style = MaterialTheme.typography.titleMedium)
            if (pending > 0) {
                Text("Ожидают отправки: $pending")
                Text(
                    "Операции будут отправлены автоматически при появлении сети. Остатки изменятся только после подтверждения сервера.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (failed > 0) {
                Text(
                    "Требуют проверки: $failed",
                    color = MaterialTheme.colorScheme.error,
                )
                Text(
                    "Сервер отклонил эти операции. Обновите остатки и повторите попытку.",
                    style = MaterialTheme.typography.bodySmall,
                )
                OutlinedButton(onClick = onRetryFailed) {
                    Text("Повторить ошибки")
                }
            }
        }
    }
}

@Composable
private fun BalanceCard(
    title: String,
    subtitle: String,
    quantity: String,
    retailPrice: BigDecimal,
    wholesalePrice: BigDecimal,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(subtitle, style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(8.dp))
            Text("Остаток: $quantity", style = MaterialTheme.typography.bodyLarge)
            Spacer(Modifier.height(4.dp))
            Text("Розница: ${retailPrice.money()} ₽")
            Text("Опт: ${wholesalePrice.money()} ₽")
        }
    }
}

@Composable
private fun EmptyCard(message: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = message,
            modifier = Modifier.padding(16.dp),
        )
    }
}

private fun BigDecimal.clean(): String = stripTrailingZeros().toPlainString()

private fun BigDecimal.money(): String = setScale(2, RoundingMode.HALF_UP).toPlainString()

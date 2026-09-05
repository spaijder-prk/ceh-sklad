package ru.ceh.sklad.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.math.BigDecimal
import java.math.RoundingMode
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import okhttp3.WebSocket
import retrofit2.HttpException
import ru.ceh.sklad.data.CehRepository
import ru.ceh.sklad.data.DocumentDto
import ru.ceh.sklad.data.QuantityLineDto
import ru.ceh.sklad.data.RepresentativeBalanceDto
import ru.ceh.sklad.data.RepresentativeDto
import ru.ceh.sklad.data.ReturnRequestDto
import ru.ceh.sklad.data.SaleLineDto
import ru.ceh.sklad.data.SaleRequestDto
import ru.ceh.sklad.data.UserDto
import ru.ceh.sklad.data.WarehouseBalanceDto
import ru.ceh.sklad.data.WarehouseDto

data class AppUiState(
    val email: String = "",
    val password: String = "",
    val loading: Boolean = false,
    val user: UserDto? = null,
    val representative: RepresentativeDto? = null,
    val warehouses: List<WarehouseDto> = emptyList(),
    val warehouseBalances: List<WarehouseBalanceDto> = emptyList(),
    val representativeBalances: List<RepresentativeBalanceDto> = emptyList(),
    val debt: BigDecimal? = null,
    val documents: List<DocumentDto> = emptyList(),
    val realtimeActive: Boolean = false,
    val operationLoading: Boolean = false,
    val operationMessage: String? = null,
    val operationError: String? = null,
    val error: String? = null,
)

class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = CehRepository(application)
    private val _state = MutableStateFlow(AppUiState())
    val state: StateFlow<AppUiState> = _state.asStateFlow()

    private var updatesSocket: WebSocket? = null

    init {
        if (repository.hasSession()) {
            refresh(startRealtime = true)
        }
    }

    fun setEmail(value: String) {
        _state.update { it.copy(email = value, error = null) }
    }

    fun setPassword(value: String) {
        _state.update { it.copy(password = value, error = null) }
    }

    fun login() {
        val email = state.value.email.trim()
        val password = state.value.password
        if (email.isBlank() || password.isBlank()) {
            _state.update { it.copy(error = "Введите email и пароль") }
            return
        }

        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            try {
                repository.login(email, password)
                loadDashboard()
                _state.update { it.copy(password = "", loading = false) }
                startRealtime()
            } catch (error: Throwable) {
                repository.logout()
                _state.update {
                    it.copy(
                        loading = false,
                        error = userMessage(error),
                    )
                }
            }
        }
    }

    fun refresh(startRealtime: Boolean = false) {
        viewModelScope.launch {
            val showLoader = state.value.user == null
            if (showLoader) {
                _state.update { it.copy(loading = true, error = null) }
            }
            try {
                loadDashboard()
                _state.update { it.copy(loading = false, error = null) }
                if (startRealtime) {
                    startRealtime()
                }
            } catch (error: Throwable) {
                handleLoadError(error)
            }
        }
    }

    fun registerSale(
        productId: String,
        quantity: BigDecimal,
        priceType: String,
        externalId: String,
    ) {
        val representative = state.value.representative ?: run {
            _state.update { it.copy(operationError = "Учетная запись не привязана к представителю") }
            return
        }
        if (state.value.operationLoading) return

        viewModelScope.launch {
            _state.update {
                it.copy(
                    operationLoading = true,
                    operationMessage = null,
                    operationError = null,
                )
            }
            try {
                val result = repository.registerSale(
                    SaleRequestDto(
                        representativeId = representative.id,
                        lines = listOf(
                            SaleLineDto(
                                productId = productId,
                                quantity = quantity,
                                priceType = priceType,
                            ),
                        ),
                        comment = "Продажа из Android-приложения",
                        externalId = externalId,
                    ),
                )
                loadDashboard()
                _state.update {
                    it.copy(
                        operationLoading = false,
                        operationMessage = "Продажа проведена. Задолженность увеличена на ${result.debtDelta.money()} ₽",
                        operationError = null,
                    )
                }
            } catch (error: Throwable) {
                handleOperationError(error)
            }
        }
    }

    fun registerReturn(
        productId: String,
        quantity: BigDecimal,
        warehouseId: String,
        externalId: String,
    ) {
        val representative = state.value.representative ?: run {
            _state.update { it.copy(operationError = "Учетная запись не привязана к представителю") }
            return
        }
        if (state.value.operationLoading) return

        viewModelScope.launch {
            _state.update {
                it.copy(
                    operationLoading = true,
                    operationMessage = null,
                    operationError = null,
                )
            }
            try {
                repository.registerReturn(
                    ReturnRequestDto(
                        representativeId = representative.id,
                        warehouseId = warehouseId,
                        lines = listOf(QuantityLineDto(productId = productId, quantity = quantity)),
                        comment = "Возврат из Android-приложения",
                        externalId = externalId,
                    ),
                )
                loadDashboard()
                _state.update {
                    it.copy(
                        operationLoading = false,
                        operationMessage = "Возврат проведен",
                        operationError = null,
                    )
                }
            } catch (error: Throwable) {
                handleOperationError(error)
            }
        }
    }

    fun clearOperationFeedback() {
        _state.update { it.copy(operationMessage = null, operationError = null) }
    }

    fun logout() {
        updatesSocket?.close(1000, "Выход пользователя")
        updatesSocket = null
        repository.logout()
        val email = state.value.email
        _state.value = AppUiState(email = email)
    }

    fun clearError() {
        _state.update { it.copy(error = null) }
    }

    override fun onCleared() {
        updatesSocket?.close(1000, "Экран закрыт")
        super.onCleared()
    }

    private suspend fun loadDashboard() {
        val dashboard = repository.loadDashboard()
        _state.update {
            it.copy(
                user = dashboard.user,
                representative = dashboard.representative,
                warehouses = dashboard.warehouses,
                warehouseBalances = dashboard.warehouseBalances,
                representativeBalances = dashboard.representativeBalances,
                debt = dashboard.debt,
                documents = dashboard.documents,
                error = null,
            )
        }
    }

    private fun startRealtime() {
        updatesSocket?.close(1000, "Переподключение")
        updatesSocket = repository.openUpdates(
            onChanged = {
                viewModelScope.launch {
                    try {
                        loadDashboard()
                    } catch (error: Throwable) {
                        handleLoadError(error)
                    }
                }
            },
            onFailure = {
                _state.update { current -> current.copy(realtimeActive = false) }
            },
        )
        _state.update { it.copy(realtimeActive = updatesSocket != null) }
    }

    private fun handleOperationError(error: Throwable) {
        if (error is HttpException && error.code() == 401) {
            handleLoadError(error)
            return
        }
        _state.update {
            it.copy(
                operationLoading = false,
                operationMessage = null,
                operationError = operationUserMessage(error),
            )
        }
    }

    private fun handleLoadError(error: Throwable) {
        if (error is HttpException && error.code() == 401) {
            updatesSocket?.cancel()
            updatesSocket = null
            repository.logout()
            val email = state.value.email
            _state.value = AppUiState(
                email = email,
                error = "Сессия истекла. Войдите снова.",
            )
            return
        }
        _state.update {
            it.copy(
                loading = false,
                operationLoading = false,
                error = userMessage(error),
            )
        }
    }

    private fun operationUserMessage(error: Throwable): String = when (error) {
        is HttpException -> when (error.code()) {
            403 -> "Недостаточно прав для операции"
            409 -> "Остаток уже изменился или товара недостаточно. Обновите данные и проверьте количество."
            422 -> "Сервер не принял данные операции. Проверьте количество и выбранные значения."
            else -> "Не удалось провести операцию: ошибка сервера ${error.code()}"
        }
        else -> "Нет ответа от сервера. Повторная отправка этой же операции безопасна."
    }

    private fun userMessage(error: Throwable): String = when (error) {
        is HttpException -> when (error.code()) {
            401 -> "Неверный email или пароль"
            403 -> "Недостаточно прав для этой учетной записи"
            else -> "Ошибка сервера: ${error.code()}"
        }
        else -> error.message ?: "Не удалось связаться с сервером"
    }
}

private fun BigDecimal.money(): String = setScale(2, RoundingMode.HALF_UP).toPlainString()

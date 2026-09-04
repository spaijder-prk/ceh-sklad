package ru.ceh.sklad.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.math.BigDecimal
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import okhttp3.WebSocket
import retrofit2.HttpException
import ru.ceh.sklad.data.CehRepository
import ru.ceh.sklad.data.RepresentativeBalanceDto
import ru.ceh.sklad.data.RepresentativeDto
import ru.ceh.sklad.data.UserDto
import ru.ceh.sklad.data.WarehouseBalanceDto

data class AppUiState(
    val email: String = "",
    val password: String = "",
    val loading: Boolean = false,
    val user: UserDto? = null,
    val representative: RepresentativeDto? = null,
    val warehouseBalances: List<WarehouseBalanceDto> = emptyList(),
    val representativeBalances: List<RepresentativeBalanceDto> = emptyList(),
    val debt: BigDecimal? = null,
    val realtimeActive: Boolean = false,
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
                warehouseBalances = dashboard.warehouseBalances,
                representativeBalances = dashboard.representativeBalances,
                debt = dashboard.debt,
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
                error = userMessage(error),
            )
        }
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

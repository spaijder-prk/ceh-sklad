package ru.ceh.sklad.data

import org.junit.Assert.assertEquals
import org.junit.Test

class LoginFeedbackTest {
    @Test
    fun invalidCredentialsStayNeutral() {
        assertEquals(
            "Неверный логин или пароль.",
            loginErrorMessage(401, null),
        )
    }

    @Test
    fun rateLimitShowsExactRetryAfterSeconds() {
        assertEquals(
            "Слишком много попыток входа. Повторите через 137 сек.",
            loginErrorMessage(429, "137"),
        )
    }

    @Test
    fun rateLimitWithoutValidHeaderUsesSafeFallback() {
        assertEquals(
            "Слишком много попыток входа. Повторите позже.",
            loginErrorMessage(429, "not-a-number"),
        )
    }

    @Test
    fun serverFailureDoesNotExposeBackendDetails() {
        assertEquals(
            "Сервер временно недоступен. Повторите попытку позже.",
            loginErrorMessage(503, null),
        )
    }
}

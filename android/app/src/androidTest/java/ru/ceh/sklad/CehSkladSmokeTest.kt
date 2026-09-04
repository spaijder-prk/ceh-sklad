package ru.ceh.sklad

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodes
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CehSkladSmokeTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun loginScreenStartsInSafeState() {
        composeRule.onNodeWithText("Цех Склад").assertIsDisplayed()
        composeRule.onNodeWithText("Вход торгового представителя").assertIsDisplayed()
        composeRule.onNodeWithText("Логин").assertIsDisplayed()
        composeRule.onNodeWithText("Пароль").assertIsDisplayed()
        composeRule.onNodeWithText("Войти").assertIsDisplayed().assertIsNotEnabled()
    }

    @Test
    fun loginButtonRequiresBothCredentials() {
        val fields = composeRule.onAllNodes(hasSetTextAction())
        fields[0].performTextInput("test-representative")
        composeRule.onNodeWithText("Войти").assertIsNotEnabled()

        fields[1].performTextInput("test-password")
        composeRule.onNodeWithText("Войти").assertIsEnabled()
    }
}

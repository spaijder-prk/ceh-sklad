package ru.ceh.sklad.data

import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class MobileSessionPolicyTest {
    @Test
    fun representativeWithLocationIsAllowed() {
        val user = UserInfo("1", "Представитель", "rep", "representative", "location-1")
        assertTrue(isMobileRepresentative(user))
        assertSame(user, requireMobileRepresentative(user))
    }

    @Test
    fun representativeWithoutLocationIsRejected() {
        val user = UserInfo("1", "Представитель", "rep", "representative", null)
        assertFalse(isMobileRepresentative(user))
        assertThrows(MobileSessionRejectedException::class.java) { requireMobileRepresentative(user) }
    }

    @Test
    fun adminAndManagerAreRejected() {
        val admin = UserInfo("1", "Администратор", "admin", "admin", null)
        val manager = UserInfo("2", "Руководитель", "manager", "manager", null)
        assertFalse(isMobileRepresentative(admin))
        assertFalse(isMobileRepresentative(manager))
        assertThrows(MobileSessionRejectedException::class.java) { requireMobileRepresentative(admin) }
        assertThrows(MobileSessionRejectedException::class.java) { requireMobileRepresentative(manager) }
    }
}

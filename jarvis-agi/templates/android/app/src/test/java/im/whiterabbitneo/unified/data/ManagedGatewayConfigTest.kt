package im.whiterabbitneo.unified.data

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ManagedGatewayConfigTest {
    @Test
    fun httpsGatewayWithLongEnrollmentCodeIsReady() {
        val config = ManagedGatewayConfig("https://agent.example.net", "0123456789abcdef", "test phone")
        assertTrue(config.isComplete)
    }

    @Test
    fun cleartextGatewayIsRejected() {
        val config = ManagedGatewayConfig("http://agent.example.net", "0123456789abcdef", "test phone")
        assertFalse(config.isComplete)
    }

    @Test
    fun shortEnrollmentCodeIsRejected() {
        val config = ManagedGatewayConfig("https://agent.example.net", "too-short", "test phone")
        assertFalse(config.isComplete)
    }
}

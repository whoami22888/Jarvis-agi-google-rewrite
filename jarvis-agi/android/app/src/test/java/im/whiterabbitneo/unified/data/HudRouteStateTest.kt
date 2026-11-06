package im.whiterabbitneo.unified.data

import org.junit.Assert.assertEquals
import org.junit.Test

class HudRouteStateTest {
    @Test
    fun localCompletionShowsLocalOllamaState() {
        val state = HudRouteStates.fromTask("completed", "local_ollama")
        assertEquals(HudRouteMode.LOCAL_OLLAMA, state.mode)
        assertEquals("Completed through the local Ollama model", state.detail)
    }

    @Test
    fun cloudFallbackShowsCloudFallbackState() {
        val state = HudRouteStates.fromTask("completed", "authorized_cloud")
        assertEquals(HudRouteMode.AUTHORIZED_CLOUD, state.mode)
        assertEquals("Local route failed; completed through the authorized cloud fallback", state.detail)
    }

    @Test
    fun blockedTaskShowsUnavailableState() {
        val state = HudRouteStates.fromTask("blocked", null)
        assertEquals(HudRouteMode.UNAVAILABLE, state.mode)
        assertEquals("No approved local or cloud route completed the request", state.detail)
    }

    @Test
    fun runningStateKeepsLocalFirstExpectationVisible() {
        assertEquals(HudRouteMode.IDLE, HudRouteStates.running.mode)
        assertEquals("Hybrid routing: local Ollama preferred…", HudRouteStates.running.detail)
    }
}

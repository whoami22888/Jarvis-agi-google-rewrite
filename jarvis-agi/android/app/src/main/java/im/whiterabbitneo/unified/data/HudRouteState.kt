package im.whiterabbitneo.unified.data

enum class HudRouteMode(val chip: String) {
    IDLE("IDLE"),
    LOCAL_OLLAMA("LOCAL OLLAMA"),
    AUTHORIZED_CLOUD("CLOUD FALLBACK"),
    UNAVAILABLE("ROUTE BLOCKED"),
}

data class HudRouteState(
    val mode: HudRouteMode,
    val detail: String,
)

object HudRouteStates {
    val idle = HudRouteState(HudRouteMode.IDLE, "Awaiting a model request")
    val running = HudRouteState(HudRouteMode.IDLE, "Hybrid routing: local Ollama preferred…")

    fun fromTask(status: String, route: String?): HudRouteState = when {
        status == "completed" && route == "local_ollama" ->
            HudRouteState(HudRouteMode.LOCAL_OLLAMA, "Completed through the local Ollama model")
        status == "completed" && route == "authorized_cloud" ->
            HudRouteState(HudRouteMode.AUTHORIZED_CLOUD, "Local route failed; completed through the authorized cloud fallback")
        status == "completed" ->
            HudRouteState(HudRouteMode.IDLE, "Completed through an unspecified approved route")
        else ->
            HudRouteState(HudRouteMode.UNAVAILABLE, "No approved local or cloud route completed the request")
    }

    fun failure(message: String) = HudRouteState(HudRouteMode.UNAVAILABLE, message)
}

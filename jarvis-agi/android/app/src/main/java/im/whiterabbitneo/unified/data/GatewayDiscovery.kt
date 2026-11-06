package im.whiterabbitneo.unified.data

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper
import java.net.URI

private const val SERVICE_TYPE = "_whiterabbit-gateway._tcp."
private const val SCAN_TIMEOUT_MILLIS = 8_000L

data class GatewayCandidate(
    val serviceName: String,
    val url: String,
)

/**
 * Discovers only owner-advertised WhiteRabbit gateway services on the current local network.
 * Discovery never sends credentials, does not pair automatically, and stops after a short scan.
 */
class GatewayDiscovery(
    context: Context,
    private val onCandidatesChanged: (List<GatewayCandidate>) -> Unit,
    private val onStatusChanged: (String) -> Unit,
) {
    private val appContext = context.applicationContext
    private val nsdManager = appContext.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val mainHandler = Handler(Looper.getMainLooper())
    private val discovered = linkedMapOf<String, GatewayCandidate>()
    private var active = false
    private var multicastLock: WifiManager.MulticastLock? = null

    private val listener = object : NsdManager.DiscoveryListener {
        override fun onDiscoveryStarted(regType: String) {
            updateStatus("Scanning the local network for advertised gateways…")
        }

        override fun onServiceFound(service: NsdServiceInfo) {
            if (!service.serviceType.startsWith("_whiterabbit-gateway._tcp", ignoreCase = true)) return
            try {
                nsdManager.resolveService(service, resolveListener)
            } catch (_: IllegalArgumentException) {
                updateStatus("A discovered gateway could not be resolved.")
            }
        }

        override fun onServiceLost(service: NsdServiceInfo) {
            mainHandler.post {
                discovered.remove(service.serviceName)
                publishCandidates()
            }
        }

        override fun onDiscoveryStopped(serviceType: String) = finish("Gateway scan complete. Select a gateway to continue.")

        override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) = finish("Gateway scan could not start (error $errorCode).")

        override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) = finish("Gateway scan stopped with error $errorCode.")
    }

    private val resolveListener = object : NsdManager.ResolveListener {
        override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
            updateStatus("Could not resolve ${serviceInfo.serviceName} (error $errorCode).")
        }

        override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
            val url = serviceInfo.advertisedHttpsUrl() ?: return
            mainHandler.post {
                discovered[serviceInfo.serviceName] = GatewayCandidate(serviceInfo.serviceName, url)
                publishCandidates()
            }
        }
    }

    fun start() {
        stop(silent = true)
        discovered.clear()
        publishCandidates()
        active = true
        acquireMulticastLock()
        try {
            nsdManager.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, listener)
            mainHandler.postDelayed({ stop() }, SCAN_TIMEOUT_MILLIS)
        } catch (error: Exception) {
            finish(error.message ?: "Gateway scan could not start.")
        }
    }

    fun stop(silent: Boolean = false) {
        mainHandler.removeCallbacksAndMessages(null)
        if (active) {
            active = false
            try {
                nsdManager.stopServiceDiscovery(listener)
            } catch (_: IllegalArgumentException) {
                // Android reports this when discovery was already stopped by the system.
            }
        }
        releaseMulticastLock()
        if (!silent) updateStatus("Gateway scan complete. Select a gateway to continue.")
    }

    private fun finish(message: String) {
        mainHandler.post {
            active = false
            releaseMulticastLock()
            updateStatus(message)
        }
    }

    private fun acquireMulticastLock() {
        val wifi = appContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return
        multicastLock = wifi.createMulticastLock("white-rabbit-gateway-discovery").apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    private fun releaseMulticastLock() {
        multicastLock?.let { lock -> if (lock.isHeld) lock.release() }
        multicastLock = null
    }

    private fun publishCandidates() = onCandidatesChanged(discovered.values.sortedBy { it.serviceName.lowercase() })

    private fun updateStatus(message: String) = mainHandler.post { onStatusChanged(message) }
}

private fun NsdServiceInfo.advertisedHttpsUrl(): String? {
    val advertised = attributes["url"]?.toString(Charsets.UTF_8)?.trim()
    if (!advertised.isNullOrBlank() && advertised.isHttpsUrl()) return advertised.trimEnd('/')

    val hostAddress = host?.hostAddress ?: return null
    val hostPart = if (hostAddress.contains(':')) "[$hostAddress]" else hostAddress
    val fallback = "https://$hostPart:$port"
    return fallback.takeIf { it.isHttpsUrl() }
}

private fun String.isHttpsUrl(): Boolean = runCatching {
    val uri = URI(this)
    uri.scheme.equals("https", ignoreCase = true) && !uri.host.isNullOrBlank()
}.getOrDefault(false)

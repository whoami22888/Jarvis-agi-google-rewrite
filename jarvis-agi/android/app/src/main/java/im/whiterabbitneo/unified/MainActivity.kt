package im.whiterabbitneo.unified

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import im.whiterabbitneo.unified.data.GatewayCandidate
import im.whiterabbitneo.unified.data.GatewayClient
import im.whiterabbitneo.unified.data.GatewayDiscovery
import im.whiterabbitneo.unified.data.HudRouteState
import im.whiterabbitneo.unified.data.HudRouteStates
import im.whiterabbitneo.unified.data.ManagedGatewayConfig
import im.whiterabbitneo.unified.data.MemoryStore
import im.whiterabbitneo.unified.data.TokenVault
import kotlinx.coroutines.launch
import org.json.JSONObject

private val Ink = Color(0xFF07110D)
private val Panel = Color(0xFF10261D)
private val Mint = Color(0xFF9EFFC8)
private val Muted = Color(0xFFB9CCBE)

enum class Destination(val label: String) { Command("Command"), Tools("Tools"), Skills("Skills"), Mcp("MCP"), Memory("Memory") }

class AgentViewModel : ViewModel() {
    var gatewayUrl by mutableStateOf("")
    var selectedGatewayUrl by mutableStateOf("")
    var paired by mutableStateOf(false)
    var enrollmentAvailable by mutableStateOf(false)
    var status by mutableStateOf("Gateway discovery pending")
    var providerState by mutableStateOf("Provider configuration will be checked after Trust & connect")
    var routeState by mutableStateOf(HudRouteStates.idle)
    var answer by mutableStateOf("")
    var enabled by mutableStateOf(setOf<String>())
    var discoveredGateways by mutableStateOf(emptyList<GatewayCandidate>())
    var scanningGateways by mutableStateOf(false)

    private lateinit var vault: TokenVault
    private lateinit var memoryStore: MemoryStore
    private lateinit var managedConfig: ManagedGatewayConfig
    private var discovery: GatewayDiscovery? = null
    private val client = GatewayClient()

    private val trustedSelection: Boolean
        get() = enrollmentAvailable && normalize(selectedGatewayUrl) == normalize(managedConfig.gatewayUrl)

    fun initialize(activity: ComponentActivity) {
        vault = TokenVault(activity)
        memoryStore = MemoryStore(activity)
        managedConfig = ManagedGatewayConfig.load(activity)
        gatewayUrl = managedConfig.gatewayUrl
        selectedGatewayUrl = managedConfig.gatewayUrl
        enrollmentAvailable = managedConfig.isComplete
        paired = vault.load() != null
        status = when {
            paired -> "Trusted gateway token stored on device"
            enrollmentAvailable -> "Select the advertised trusted gateway or connect to the managed gateway"
            else -> "Managed gateway configuration is required before enrollment"
        }
        discovery = GatewayDiscovery(
            activity,
            onCandidatesChanged = { discoveredGateways = it },
            onStatusChanged = { message ->
                status = message
                if (!message.startsWith("Scanning")) scanningGateways = false
            },
        )
    }

    fun scanForGateways() {
        if (!::vault.isInitialized) return
        scanningGateways = true
        status = "Scanning the local network for advertised gateways…"
        discovery?.start()
    }

    fun selectGateway(candidate: GatewayCandidate) {
        selectedGatewayUrl = candidate.url
        if (trustedSelection) {
            gatewayUrl = managedConfig.gatewayUrl
            status = "Selected the managed trusted gateway: ${candidate.serviceName}."
        } else {
            status = if (enrollmentAvailable) {
                "${candidate.serviceName} is not the gateway approved by this device configuration."
            } else {
                "${candidate.serviceName} was discovered, but this device has no managed enrollment configuration."
            }
        }
    }

    private fun readiness(localEnabled: Boolean, localModel: String, cloudEnabled: Boolean, cloudModel: String): String = when {
        localEnabled -> "Local Ollama configured: $localModel"
        cloudEnabled -> "Authorized cloud fallback configured: $cloudModel"
        else -> "Provider configuration required: enable local Ollama or an authorized cloud fallback"
    }

    suspend fun trustAndConnect() {
        try {
            check(enrollmentAvailable) { "Managed gateway configuration is not available" }
            check(trustedSelection) { "Select the advertised gateway approved for this device before connecting" }
            status = "Checking trusted gateway…"
            val health = client.health(gatewayUrl)
            providerState = readiness(health.localOllamaEnabled, health.localOllamaModel, health.authorizedCloudFallbackEnabled, health.cloudModel)
            val result = client.pair(gatewayUrl, managedConfig.deviceName, managedConfig.enrollmentCode)
            vault.save(result.token)
            paired = true
            routeState = HudRouteStates.idle
            status = "Trusted gateway connected as ${result.deviceId.take(8)}…"
        } catch (e: Exception) {
            routeState = HudRouteStates.failure(e.message ?: "Trusted gateway connection failed")
            status = routeState.detail
        }
    }

    suspend fun refreshReadiness() {
        try {
            val health = client.health(gatewayUrl)
            providerState = readiness(health.localOllamaEnabled, health.localOllamaModel, health.authorizedCloudFallbackEnabled, health.cloudModel)
            status = "Gateway readiness refreshed"
        } catch (e: Exception) {
            providerState = e.message ?: "Gateway readiness unavailable"
        }
    }

    fun disconnect() {
        if (::vault.isInitialized) vault.clear()
        paired = false
        answer = ""
        routeState = HudRouteStates.idle
        status = "Gateway disconnected. Select and connect a trusted gateway to continue."
    }

    suspend fun run(prompt: String) { try { val token = vault.load() ?: error("Connect to the trusted gateway first"); routeState = HudRouteStates.running; status = routeState.detail; val result = client.task(gatewayUrl, token, prompt, enabled); routeState = HudRouteStates.fromTask(result.status, result.route); status = routeState.detail; answer = result.answer } catch (e: Exception) { routeState = HudRouteStates.failure(e.message ?: "Task failed"); status = routeState.detail } }
    suspend fun addRegistry(kind: String, name: String, definition: JSONObject) { try { val token = vault.load() ?: error("Connect to the trusted gateway first"); client.createRegistryItem(gatewayUrl, token, kind, name, definition); status = "$kind added to registry" } catch (e: Exception) { status = e.message ?: "Registry update failed" } }
    fun memory(): List<String> = if (::memoryStore.isInitialized) memoryStore.list() else emptyList()
    fun addMemory(note: String) { memoryStore.add(note) }
    fun deleteMemory(note: String) { memoryStore.delete(note) }
    override fun onCleared() { discovery?.stop(silent = true); super.onCleared() }

    private fun normalize(value: String): String = value.trimEnd('/').lowercase()
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState); setContent { WhiteRabbitApp(this) } }
}

@Composable
fun WhiteRabbitApp(activity: ComponentActivity, vm: AgentViewModel = viewModel()) {
    LaunchedEffect(Unit) { vm.initialize(activity) }
    var destination by remember { mutableStateOf(Destination.Command) }
    MaterialTheme(colorScheme = darkColorScheme(primary = Mint, secondary = Mint, surface = Panel, background = Ink, onPrimary = Ink, onBackground = Color.White)) {
        Scaffold(containerColor = Ink, bottomBar = {
            NavigationBar(containerColor = Panel) { Destination.entries.forEach { item -> NavigationBarItem(selected = destination == item, onClick = { destination = item }, icon = { Text(item.label.take(1), color = Mint, fontWeight = FontWeight.Bold) }, label = { Text(item.label) }) } }
        }) { padding -> Column(Modifier.fillMaxSize().padding(padding).padding(16.dp)) {
            Text("WHITE RABBIT NEO", color = Mint, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Black)
            Text("Unified agent HUD · hybrid DeepSeek routing", color = Color.White, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp)); StatusCard(vm.status, vm.paired, vm.routeState)
            Spacer(Modifier.height(12.dp))
            when (destination) {
                Destination.Command -> CommandScreen(vm)
                Destination.Tools -> RegistryScreen(vm, "tool", "Tools", "Create permission-scoped web, API, or automation-proposal tools.")
                Destination.Skills -> RegistryScreen(vm, "skill", "Skills", "Save reusable agent instructions with explicit allowed tools.")
                Destination.Mcp -> RegistryScreen(vm, "mcp", "MCP Registry", "Store trusted MCP endpoint metadata. Credentials remain on the authorized gateway.")
                Destination.Memory -> MemoryScreen(vm)
            }
        } }
    }
}

@Composable private fun StatusCard(status: String, paired: Boolean, routeState: HudRouteState) = Card(colors = CardDefaults.cardColors(containerColor = Panel), shape = RoundedCornerShape(14.dp)) { Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) { Column { Text(if (paired) "SECURE GATEWAY LINK" else "SETUP REQUIRED", color = Mint, style = MaterialTheme.typography.labelMedium); Text(status, color = Muted, style = MaterialTheme.typography.bodySmall) }; AssistChip(onClick = {}, label = { Text(if (paired) routeState.mode.chip else "OFFLINE") }) } }

@Composable private fun CommandScreen(vm: AgentViewModel) { val scope = rememberCoroutineScope(); var prompt by remember { mutableStateOf("") }; var web by remember { mutableStateOf(false) }; var api by remember { mutableStateOf(false) }; var automation by remember { mutableStateOf(false) }; Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
    Card(colors = CardDefaults.cardColors(containerColor = Panel)) { Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("TRUSTED GATEWAY SETUP", color = Mint, fontWeight = FontWeight.Bold)
        Text(if (vm.enrollmentAvailable) vm.gatewayUrl else "Managed gateway configuration unavailable", color = Muted, style = MaterialTheme.typography.bodySmall)
        Text(vm.providerState, color = Muted, style = MaterialTheme.typography.bodySmall)
        Button(onClick = { vm.scanForGateways() }, enabled = !vm.scanningGateways, modifier = Modifier.fillMaxWidth()) { Text(if (vm.scanningGateways) "Scanning local network…" else "Find local gateways") }
        if (vm.discoveredGateways.isNotEmpty()) {
            Text("Advertised local gateways", color = Mint, fontWeight = FontWeight.Bold)
            vm.discoveredGateways.forEach { candidate ->
                OutlinedButton(onClick = { vm.selectGateway(candidate) }, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.fillMaxWidth()) { Text(candidate.serviceName); Text(candidate.url, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
        Text("Discovery does not grant access. The selected gateway must match the device-owner HTTPS configuration before the hidden managed enrollment code can authorize this device.", color = Muted, style = MaterialTheme.typography.bodySmall)
        if (!vm.paired) {
            Button(onClick = { scope.launch { vm.trustAndConnect() } }, enabled = vm.enrollmentAvailable, modifier = Modifier.fillMaxWidth()) { Text("Trust & connect") }
        } else {
            OutlinedButton(onClick = { scope.launch { vm.refreshReadiness() } }, modifier = Modifier.fillMaxWidth()) { Text("Refresh gateway readiness") }
            OutlinedButton(onClick = { vm.disconnect() }, modifier = Modifier.fillMaxWidth()) { Text("Disconnect gateway") }
        }
    } }
    Text("Capability selection", color = Mint, fontWeight = FontWeight.Bold)
    CapabilityToggle("Web read — public HTTPS only", web) { web = it; vm.enabled = vm.enabled.toMutableSet().apply { if (it) add("web_read") else remove("web_read") } }
    CapabilityToggle("API calls — gateway-authorized only", api) { api = it; vm.enabled = vm.enabled.toMutableSet().apply { if (it) add("api_call") else remove("api_call") } }
    CapabilityToggle("Automation — always proposed, never silent", automation) { automation = it; vm.enabled = vm.enabled.toMutableSet().apply { if (it) add("automation") else remove("automation") } }
    OutlinedTextField(value = prompt, onValueChange = { prompt = it }, label = { Text("Ask the unified agent") }, modifier = Modifier.fillMaxWidth().height(140.dp))
    Button(onClick = { scope.launch { vm.run(prompt) } }, enabled = vm.paired && prompt.isNotBlank(), modifier = Modifier.fillMaxWidth()) { Text("Run unified agent") }
    if (vm.answer.isNotBlank()) Card(colors = CardDefaults.cardColors(containerColor = Panel)) { Text(vm.answer, Modifier.padding(14.dp), color = Color.White) }
} }

@Composable private fun CapabilityToggle(label: String, checked: Boolean, changed: (Boolean) -> Unit) = Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) { Switch(checked = checked, onCheckedChange = changed); Spacer(Modifier.width(10.dp)); Text(label, color = Muted, style = MaterialTheme.typography.bodyMedium) }

@Composable private fun RegistryScreen(vm: AgentViewModel, kind: String, title: String, guidance: String) { val scope = rememberCoroutineScope(); var name by remember { mutableStateOf("") }; var detail by remember { mutableStateOf("") }; Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) { Text(title, color = Mint, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold); Text(guidance, color = Muted); OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, modifier = Modifier.fillMaxWidth()); OutlinedTextField(value = detail, onValueChange = { detail = it }, label = { Text(if (kind == "skill") "Instructions" else "HTTPS endpoint or description") }, modifier = Modifier.fillMaxWidth()); Button(onClick = { val definition = when (kind) { "tool" -> JSONObject().put("mode", "web_read").put("url", detail.ifBlank { "https://example.com" }); "skill" -> JSONObject().put("instructions", detail); else -> JSONObject().put("transport", "streamable_http").put("endpoint", detail) }; scope.launch { vm.addRegistry(kind, name.ifBlank { "Untitled $kind" }, definition) } }, enabled = vm.paired, modifier = Modifier.fillMaxWidth()) { Text("Register $kind") }; Text("All registrations remain inert until a user approves a supported gateway invocation.", color = Muted, style = MaterialTheme.typography.bodySmall) } }

@Composable private fun MemoryScreen(vm: AgentViewModel) { var note by remember { mutableStateOf("") }; var notes by remember { mutableStateOf(vm.memory()) }; Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) { Text("Persistent Memory", color = Mint, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold); Text("Notes stay on this device until you delete them.", color = Muted); OutlinedTextField(value = note, onValueChange = { note = it }, label = { Text("Memory note") }, modifier = Modifier.fillMaxWidth()); Button(onClick = { if (note.isNotBlank()) { vm.addMemory(note); notes = vm.memory(); note = "" } }, modifier = Modifier.fillMaxWidth()) { Text("Store locally") }; notes.forEach { item -> Card(colors = CardDefaults.cardColors(containerColor = Panel)) { Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) { Text(item, color = Color.White, modifier = Modifier.weight(1f)); TextButton(onClick = { vm.deleteMemory(item); notes = vm.memory() }) { Text("Delete") } } } } } }

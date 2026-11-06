package im.whiterabbitneo.unified.data

import android.content.Context
import android.content.RestrictionsManager

data class ManagedGatewayConfig(
    val gatewayUrl: String,
    val enrollmentCode: String,
    val deviceName: String,
) {
    val isComplete: Boolean
        get() = gatewayUrl.startsWith("https://") && enrollmentCode.length >= 16

    companion object {
        private const val GATEWAY_URL = "gateway_url"
        private const val ENROLLMENT_CODE = "enrollment_code"
        private const val DEVICE_NAME = "device_name"

        fun load(context: Context): ManagedGatewayConfig {
            val restrictions = (context.getSystemService(Context.RESTRICTIONS_SERVICE) as RestrictionsManager)
                .applicationRestrictions
            return ManagedGatewayConfig(
                gatewayUrl = restrictions.getString(GATEWAY_URL, "").trimEnd('/'),
                enrollmentCode = restrictions.getString(ENROLLMENT_CODE, ""),
                deviceName = restrictions.getString(DEVICE_NAME, "WhiteRabbit Neo Android"),
            )
        }
    }
}

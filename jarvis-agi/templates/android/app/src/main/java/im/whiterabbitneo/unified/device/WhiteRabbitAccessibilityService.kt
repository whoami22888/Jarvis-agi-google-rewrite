package im.whiterabbitneo.unified.device

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent

class WhiteRabbitAccessibilityService : AccessibilityService() {
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // No event contents are collected, stored, or transmitted. Actions are only added after a local approval flow.
    }
    override fun onInterrupt() = Unit
}

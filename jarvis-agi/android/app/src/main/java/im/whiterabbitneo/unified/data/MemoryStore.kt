package im.whiterabbitneo.unified.data

import android.content.Context
import org.json.JSONArray

class MemoryStore(context: Context) {
    private val prefs = context.getSharedPreferences("wrn_memory", Context.MODE_PRIVATE)
    fun list(): List<String> = JSONArray(prefs.getString("notes", "[]") ?: "[]").let { data -> List(data.length()) { data.getString(it) } }
    fun add(note: String) {
        val updated = JSONArray(list()).put(note.trim())
        prefs.edit().putString("notes", updated.toString()).apply()
    }
    fun delete(note: String) { prefs.edit().putString("notes", JSONArray(list().filterNot { it == note }).toString()).apply() }
}

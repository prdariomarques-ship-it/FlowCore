package com.flowcore.android

import android.os.Bundle
import android.text.method.ScrollingMovementMethod
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * FlowCore Android — cliente do FlowCore Core rodando no Termux (localhost:8080).
 * Abas: Radar (Macro Score + Regime) | Agente (chat LLM local-first) | Notas | Status
 */
class MainActivity : AppCompatActivity() {

    private val executor = Executors.newSingleThreadExecutor()

    /** Base URL do Core — o FlowCore no Termux expõe a API em localhost:8080.
     *  Editável via campo na aba Status, persistido em SharedPreferences. */
    private var baseUrl: String
        get() = getSharedPreferences("flowcore", 0).getString("base_url", "http://127.0.0.1:8080")!!
        set(value) = getSharedPreferences("flowcore", 0).edit().putString("base_url", value).apply()

    private val apiToken: String
        get() = getSharedPreferences("flowcore", 0).getString("api_token", "")!!

    private lateinit var root: LinearLayout
    private lateinit var content: LinearLayout
    private var currentTab = "radar"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            setBackgroundColor(android.graphics.Color.parseColor("#0a0f1e"))
        }
        setContentView(root)
        renderHeader()
        renderTabs()
        showTab("radar")
    }

    /* ── Header ───────────────────────────────────────────── */
    private fun renderHeader() {
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(36, 28, 36, 28)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        val logo = TextView(this).apply {
            text = "F"
            textSize = 17f
            gravity = Gravity.CENTER
            setTextColor(android.graphics.Color.WHITE)
            val lp = LinearLayout.LayoutParams(96, 96)
            lp.marginEnd = 28
            layoutParams = lp
            background = android.graphics.drawable.GradientDrawable().apply {
                setColor(android.graphics.Color.parseColor("#111827"))
                cornerRadius = 18f
            }
        }
        val titleBlock = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        val title = TextView(this).apply {
            text = "FlowCore"
            textSize = 20f
            setTextColor(android.graphics.Color.parseColor("#00d4ff"))
        }
        val sub = TextView(this).apply {
            text = "Radar de Mercado · Agente · Notas"
            textSize = 11f
            setTextColor(android.graphics.Color.parseColor("#94a3b8"))
        }
        titleBlock.addView(title)
        titleBlock.addView(sub)
        header.addView(logo)
        header.addView(titleBlock)
        root.addView(header)
    }

    /* ── Tabs ─────────────────────────────────────────────── */
    private fun renderTabs() {
        val tabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(24, 0, 24, 0)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        listOf("radar" to "Radar", "agente" to "Agente", "notas" to "Notas", "status" to "Status").forEach { (key, label) ->
            val btn = Button(this).apply {
                text = label
                textSize = 12f
                setTextColor(if (key == currentTab)
                    android.graphics.Color.parseColor("#00d4ff") else
                    android.graphics.Color.parseColor("#94a3b8"))
                setBackgroundColor(android.graphics.Color.parseColor("#1a2235"))
                isSingleLine = true
                val lp = LinearLayout.LayoutParams(0, 130)
                lp.weight = 1f
                lp.marginStart = 10
                lp.marginEnd = 10
                lp.topMargin = 12
                layoutParams = lp
                setOnClickListener { currentTab = key; renderTabs(); content.removeAllViews(); showTab(key) }
            }
            tabs.addView(btn)
        }
        root.addView(tabs)
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 24, 36, 36)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        }
        root.addView(ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0
            ).apply { weight = 1f }
            addView(content)
        })
    }

    /* ── Tab content ──────────────────────────────────────── */
    private fun showTab(tab: String) {
        content.removeAllViews()
        when (tab) {
            "radar" -> {
                content.addView(quickSection("MACRO SCORE · REGIME DE MERCADO"))
                content.addView(actionButton("Atualizar scores") { get("/api/macro-score/scores", it as TextView) })
                content.addView(actionButton("Dimensões") { get("/api/macro-score/dimensions", it as TextView) })
                content.addView(actionButton("Sinais de regime") { get("/api/regime/signals", it as TextView) })
                content.addView(actionButton("Observer (eventos)") { get("/api/observer/events", it as TextView) })
                content.addView(out())
            }
            "agente" -> {
                content.addView(quickSection("AGENTE · LLM LOCAL-FIRST (OLLAMA → CLOUD)"))
                val chat = TextView(this).apply {
                    textSize = 13f
                    setTextColor(android.graphics.Color.parseColor("#e2e8f0"))
                    movementMethod = ScrollingMovementMethod()
                    setPadding(24, 24, 24, 24)
                    background = android.graphics.drawable.GradientDrawable().apply {
                        setColor(android.graphics.Color.parseColor("#111827")); cornerRadius = 24f
                    }
                    layoutParams = ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, 480
                    )
                }
                content.addView(chat)
                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    layoutParams = ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT
                    )
                }
                val input = EditText(this).apply {
                    hint = "Pergunte ao FlowCore..."
                    textSize = 14f
                    setTextColor(android.graphics.Color.parseColor("#e2e8f0"))
                    setHintTextColor(android.graphics.Color.parseColor("#94a3b8"))
                    isSingleLine = true
                    val lp = LinearLayout.LayoutParams(0, 140)
                    lp.weight = 1f
                    lp.marginEnd = 16
                    layoutParams = lp
                    background = android.graphics.drawable.GradientDrawable().apply {
                        setColor(android.graphics.Color.parseColor("#1a2235")); cornerRadius = 14f
                    }
                }
                val send = Button(this).apply {
                    text = "Enviar"
                    textSize = 12f
                    setTextColor(android.graphics.Color.WHITE)
                    setBackgroundColor(android.graphics.Color.parseColor("#00d4ff"))
                    isSingleLine = true
                    val lp = LinearLayout.LayoutParams(220, 140)
                    layoutParams = lp
                    setOnClickListener {
                        val q = input.text.toString().trim()
                        if (q.isEmpty()) return@setOnClickListener
                        chat.append("Você: $q\n\n")
                        askAgent(q, chat)
                        input.text.clear()
                    }
                }
                row.addView(input)
                row.addView(send)
                content.addView(row)
            }
            "notas" -> {
                content.addView(quickSection("NOTAS E MEMÓRIAS"))
                content.addView(actionButton("Listar notas") { get("/api/notes", it as TextView) })
                content.addView(actionButton("Memórias") { get("/api/memories", it as TextView) })
                content.addView(out())
            }
            "status" -> {
                content.addView(quickSection("STATUS DO CORE E INTEGRAÇÕES"))
                content.addView(actionButton("Health") { get("/api/health", it as TextView) })
                content.addView(actionButton("Status completo") { get("/api/status", it as TextView) })
                content.addView(actionButton("Integrações") { get("/api/integrations/status", it as TextView) })
                content.addView(actionButton("LLM Router") { get("/api/llm/status", it as TextView) })
                content.addView(actionButton("WhatsApp") { get("/api/whatsapp/status", it as TextView) })
                content.addView(actionButton("Telegram") { get("/api/telegram/config", it as TextView) })
                content.addView(actionButton("Outlook (não lidas)") { get("/api/outlook/unread", it as TextView) })
                content.addView(out())
                // Configuração da URL do Core
                val urlRow = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    layoutParams = LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT
                    ).apply { topMargin = 24 }
                }
                val et = EditText(this).apply {
                    setText(baseUrl)
                    hint = "http://127.0.0.1:8080"
                    textSize = 12f
                    setTextColor(android.graphics.Color.parseColor("#e2e8f0"))
                    setHintTextColor(android.graphics.Color.parseColor("#94a3b8"))
                    isSingleLine = true
                    val lp = LinearLayout.LayoutParams(0, 120)
                    lp.weight = 1f
                    lp.marginEnd = 16
                    layoutParams = lp
                }
                val save = Button(this).apply {
                    text = "Salvar URL"
                    textSize = 11f
                    setTextColor(android.graphics.Color.WHITE)
                    setBackgroundColor(android.graphics.Color.parseColor("#7c3aed"))
                    isSingleLine = true
                    val lp = LinearLayout.LayoutParams(240, 120)
                    layoutParams = lp
                    setOnClickListener {
                        val u = et.text.toString().trim().trimEnd('/')
                        if (u.isNotEmpty()) {
                            baseUrl = u
                            Toast.makeText(this@MainActivity, "URL salva: $u", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
                urlRow.addView(et)
                urlRow.addView(save)
                content.addView(urlRow)
            }
        }
    }

    /* ── Helpers ──────────────────────────────────────────── */
    private fun quickSection(label: String): TextView = TextView(this).apply {
        text = label
        textSize = 11f
        setTextColor(android.graphics.Color.parseColor("#94a3b8"))
        setPadding(0, 16, 0, 16)
    }

    private fun actionButton(label: String, onClick: (View) -> Unit): Button = Button(this).apply {
        text = label
        textSize = 13f
        setTextColor(android.graphics.Color.parseColor("#00d4ff"))
        setBackgroundColor(android.graphics.Color.parseColor("#1a2235"))
        isSingleLine = true
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            140
        ).apply { topMargin = 12 }
        setOnClickListener(onClick)
    }

    private fun out(): TextView = TextView(this).apply {
        textSize = 11f
        setTextColor(android.graphics.Color.parseColor("#e2e8f0"))
        setPadding(20, 20, 20, 20)
        background = android.graphics.drawable.GradientDrawable().apply {
            setColor(android.graphics.Color.parseColor("#111827")); cornerRadius = 18f
        }
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = 16 }
        text = "Toque em um botão para consultar o Core…"
    }

    private fun get(endpoint: String, target: TextView) {
        target.text = "GET $endpoint …"
        executor.execute {
            val result = request("GET", endpoint, null)
            runOnUiThread { target.text = formatJson(result) }
        }
    }

    private fun askAgent(question: String, chat: TextView) {
        val body = """{"question":${escapeJson(question)}}"""
        executor.execute {
            val result = request("POST", "/api/ask", body)
            runOnUiThread {
                if (result.startsWith("HTTP") || result.contains("Exception") || result.contains("ConnectException")) {
                    chat.append("Erro: $result\n\n")
                    return@runOnUiThread
                }
                val answer = try {
                    val root = org.json.JSONObject(result)
                    root.optString("answer", result)
                } catch (e: Exception) { result }
                chat.append("FlowCore: $answer\n\n")
            }
        }
    }

    private fun request(method: String, endpoint: String, body: String?): String {
        val connection = (URL(baseUrl + endpoint).openConnection() as HttpURLConnection)
        return try {
            connection.requestMethod = method
            connection.connectTimeout = 8000
            connection.readTimeout = 90000
            connection.setRequestProperty("Content-Type", "application/json")
            val token = apiToken
            if (token.isNotEmpty()) {
                connection.setRequestProperty("X-FlowCore-Token", token)
            }
            if (body != null) {
                connection.doOutput = true
                connection.outputStream.write(body.toByteArray())
                connection.outputStream.flush()
            }
            val stream = if (connection.responseCode >= 400) connection.errorStream else connection.inputStream
            val text = stream?.bufferedReader()?.use { BufferedReader(it).readText() }.orEmpty()
            if (connection.responseCode >= 400) "HTTP ${connection.responseCode}: $text" else text
        } catch (error: Exception) {
            "${error::class.java.simpleName}: ${error.message ?: error}"
        } finally {
            connection.disconnect()
        }
    }

    private fun formatJson(raw: String): String {
        val json = try {
            org.json.JSONArray(raw).toString(2)
        } catch (e: Exception) {
            try {
                org.json.JSONObject(raw).toString(2)
            } catch (e2: Exception) { raw }
        }
        return json
    }

    private fun escapeJson(s: String): String =
        "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\""

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }
}

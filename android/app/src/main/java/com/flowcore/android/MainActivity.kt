package com.flowcore.android

import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.SpannableString
import android.text.Spanned
import android.text.method.LinkMovementMethod
import android.text.method.ScrollingMovementMethod
import android.text.style.ForegroundColorSpan
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.cardview.widget.CardView
import com.google.android.material.button.MaterialButton
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * FlowCore Android (redesign v1.8) — cliente do FlowCore Core rodando no Termux.
 * Abas: Radar (Macro Score + Regime) | Agente (chat LLM local-first) | Notas | Status
 * Visual: Material 3 dark com cartão de cabeçalho em gradiente, tabs em chips,
 * cartões elevados e saída em bloco de código.
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

    private val C_PRIMARY = Color.parseColor("#EEF2FF")
    private val C_SECONDARY = Color.parseColor("#94A3B8")
    private val C_ACCENT = Color.parseColor("#00D4FF")
    private val C_VIOLET = Color.parseColor("#7C3AED")
    private val C_SUCCESS = Color.parseColor("#34D399")
    private val C_ERROR = Color.parseColor("#F87171")
    private val C_ON_ACCENT = Color.parseColor("#06141F")

    private lateinit var root: LinearLayout
    private lateinit var tabsRow: LinearLayout
    private lateinit var content: LinearLayout
    private var currentTab = "radar"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            try {
                val sw = java.io.StringWriter()
                e.printStackTrace(java.io.PrintWriter(sw))
                val log = "CRASH: ${t.name}\n${sw.toString()}"
                android.util.Log.e("FlowCore", log)
                getExternalFilesDir(null)?.let { dir ->
                    java.io.File(dir, "crash.txt").writeText(log)
                }
            } catch (ignored: Throwable) {}
        }
        try {
            root = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT
                )
                setBackgroundColor(Color.parseColor("#0A0F1E"))
            }
            setContentView(root)
            renderHeader()
            renderTabs()
            showTab("radar")
        } catch (e: Exception) {
            val tv = TextView(this).apply {
                textSize = 14f
                setTextColor(Color.RED)
                setPadding(40, 40, 40, 40)
                text = "Erro ao montar a tela:\n${e::class.java.name}\n${e.message}\nLog: ${getExternalFilesDir(null)}/crash.txt"
            }
            setContentView(tv)
            val sw = java.io.StringWriter()
            e.printStackTrace(java.io.PrintWriter(sw))
            try { getExternalFilesDir(null)?.let { dir -> java.io.File(dir, "crash.txt").writeText(sw.toString()) } } catch (ignored: Throwable) {}
        }
    }

    /* ── Header com gradiente e logo ─────────────────────── */
    private fun renderHeader() {
        val header = CardView(this).apply {
            radius = 0f
            cardElevation = 0f
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
            setCardBackgroundColor(Color.parseColor("#0E2A47"))
        }
        val banner = GradientDrawable(
            GradientDrawable.Orientation.TL_BR,
            intArrayOf(Color.parseColor("#0E2A47"), Color.parseColor("#0A0F1E"))
        )
        val inner = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(36, 44, 36, 44)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
            background = banner
        }
        val logo = TextView(this).apply {
            text = "F"
            textSize = 20f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            setTextColor(C_ACCENT)
            layoutParams = LinearLayout.LayoutParams(130, 130).apply {
                marginEnd = 28
            }
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#00D4FF"))
                cornerRadius = 32f
            }
        }
        val titleBlock = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { gravity = Gravity.CENTER_VERTICAL }
        }
        val title = TextView(this).apply {
            text = "FlowCore"
            textSize = 26f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(C_PRIMARY)
        }
        val sub = TextView(this).apply {
            text = "Radar de Mercado · Agente · Notas"
            textSize = 12f
            setTextColor(C_ACCENT)
        }
        titleBlock.addView(title)
        titleBlock.addView(sub)
        inner.addView(logo)
        inner.addView(titleBlock)
        header.addView(inner)
        root.addView(header)
    }

    /* ── Tabs como chips Material ────────────────────────── */
    private fun renderTabs() {
        tabsRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(20, 24, 20, 16)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        val entries = listOf(
            "radar" to "Radar",
            "agente" to "Agente",
            "notas" to "Notas",
            "status" to "Status"
        )
        entries.forEachIndexed { idx, (key, label) ->
            val btn = MaterialButton(this).apply {
                text = label
                isSingleLine = true
                textSize = 12f
                layoutParams = LinearLayout.LayoutParams(0, 120).apply {
                    weight = 1f
                    marginStart = if (idx == 0) 0 else 12
                    marginEnd = if (idx == entries.size - 1) 0 else 0
                }
                if (key == currentTab) {
                    setBackgroundColor(C_ACCENT)
                    setTextColor(C_ON_ACCENT)
                } else {
                    setBackgroundColor(Color.parseColor("#1A2235"))
                    setTextColor(C_SECONDARY)
                }
                val radius = 24f
                val shape = GradientDrawable().apply {
                    shape = GradientDrawable.RECTANGLE
                    cornerRadius = radius
                    if (key == currentTab) setColor(C_ACCENT) else setColor(Color.parseColor("#1A2235"))
                }
                background = shape
                setOnClickListener { currentTab = key; renderTabs(); showTab(key) }
            }
            tabsRow.addView(btn)
        }
        root.addView(tabsRow)

        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 8, 36, 40)
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

    private fun clearBody() {
        while (root.childCount > 2) root.removeViewAt(2)
        content.removeAllViews()
    }

    /* ── Conteúdo das abas ───────────────────────────────── */
    private fun showTab(tab: String) {
        content.removeAllViews()
        when (tab) {
            "radar" -> {
                content.addView(sectionTitle("Macro Score · Regime de Mercado"))
                content.addView(actionButton("Atualizar scores", C_ACCENT) { get("/api/macro-score/scores", it as TextView) })
                content.addView(actionButton("Dimensões", C_ACCENT) { get("/api/macro-score/dimensions", it as TextView) })
                content.addView(actionButton("Sinais de regime", C_ACCENT) { get("/api/regime/signals", it as TextView) })
                content.addView(actionButton("Observer (eventos)", C_ACCENT) { get("/api/observer/events", it as TextView) })
                content.addView(out())
            }
            "agente" -> {
                content.addView(sectionTitle("Agente · LLM local-first (Ollama → Cloud)"))
                val chat = TextView(this).apply {
                    textSize = 14f
                    setTextColor(C_PRIMARY)
                    movementMethod = ScrollingMovementMethod()
                    setPadding(28, 28, 28, 28)
                    background = GradientDrawable().apply {
                        setColor(Color.parseColor("#111827"))
                        cornerRadius = 24f
                    }
                    layoutParams = ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        480
                    )
                }
                content.addView(chat)
                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    layoutParams = LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT
                    ).apply { topMargin = 20 }
                }
                val input = EditText(this).apply {
                    hint = "Pergunte ao FlowCore..."
                    textSize = 14f
                    setTextColor(C_PRIMARY)
                    setHintTextColor(C_SECONDARY)
                    isSingleLine = true
                    val lp = LinearLayout.LayoutParams(0, 140)
                    lp.weight = 1f
                    lp.marginEnd = 16
                    layoutParams = lp
                    background = GradientDrawable().apply {
                        setColor(Color.parseColor("#1A2235"))
                        cornerRadius = 24f
                    }
                }
                val send = MaterialButton(this).apply {
                    text = "Enviar"
                    textSize = 13f
                    isSingleLine = true
                    layoutParams = LinearLayout.LayoutParams(220, 140)
                    setTextColor(C_ON_ACCENT)
                    background = GradientDrawable().apply {
                        setColor(C_ACCENT)
                        cornerRadius = 24f
                    }
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
                content.addView(sectionTitle("Notas e Memórias"))
                content.addView(actionButton("Listar notas", C_ACCENT) { get("/api/notes", it as TextView) })
                content.addView(actionButton("Memórias", C_ACCENT) { get("/api/memories", it as TextView) })
                content.addView(out())
            }
            "status" -> {
                content.addView(sectionTitle("Status do Core e Integrações"))
                content.addView(actionButton("Health", C_SUCCESS) { get("/api/health", it as TextView) })
                content.addView(actionButton("Status completo", C_SUCCESS) { get("/api/status", it as TextView) })
                content.addView(actionButton("Integrações", C_SUCCESS) { get("/api/integrations/status", it as TextView) })
                content.addView(actionButton("LLM Router", C_SUCCESS) { get("/api/llm/status", it as TextView) })
                content.addView(actionButton("WhatsApp", C_SUCCESS) { get("/api/whatsapp/status", it as TextView) })
                content.addView(actionButton("Telegram", C_SUCCESS) { get("/api/telegram/config", it as TextView) })
                content.addView(actionButton("Outlook (não lidas)", C_SUCCESS) { get("/api/outlook/unread", it as TextView) })
                content.addView(out())
                content.addView(sectionTitle("Conexão com o Core"))
                val urlRow = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    layoutParams = LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT
                    ).apply { topMargin = 8 }
                }
                val et = EditText(this).apply {
                    setText(baseUrl)
                    hint = "http://127.0.0.1:8080"
                    textSize = 12f
                    setTextColor(C_PRIMARY)
                    setHintTextColor(C_SECONDARY)
                    isSingleLine = true
                    val lp = LinearLayout.LayoutParams(0, 120)
                    lp.weight = 1f
                    lp.marginEnd = 16
                    lp.topMargin = 24
                    layoutParams = lp
                    background = GradientDrawable().apply {
                        setColor(Color.parseColor("#1A2235"))
                        cornerRadius = 18f
                    }
                }
                val save = MaterialButton(this).apply {
                    text = "Salvar URL"
                    textSize = 11f
                    isSingleLine = true
                    layoutParams = LinearLayout.LayoutParams(240, 120)
                    setTextColor(Color.WHITE)
                    background = GradientDrawable().apply {
                        setColor(C_VIOLET)
                        cornerRadius = 24f
                    }
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

    /* ── Helpers de layout ───────────────────────────────── */
    private fun sectionTitle(label: String): TextView = TextView(this).apply {
        text = label.uppercase()
        textSize = 12f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(C_ACCENT)
        letterSpacing = 0.08f
        setPadding(0, 24, 0, 16)
    }

    private fun actionButton(label: String, color: Int, onClick: (View) -> Unit): MaterialButton {
        return MaterialButton(this).apply {
            text = label
            textSize = 13f
            isSingleLine = true
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                150
            ).apply { topMargin = 12 }
            setTextColor(color)
            setTextColor(C_PRIMARY)
            val shape = GradientDrawable().apply {
                setColor(Color.parseColor("#1A2235"))
                cornerRadius = 18f
            }
            background = shape
            setOnClickListener(onClick)
        }
    }

    private fun out(): TextView = TextView(this).apply {
        textSize = 12f
        setTextColor(C_PRIMARY)
        setPadding(24, 24, 24, 24)
        background = GradientDrawable().apply {
            setColor(Color.parseColor("#111827"))
            cornerRadius = 24f
        }
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = 20 }
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

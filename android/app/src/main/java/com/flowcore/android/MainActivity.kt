package com.flowcore.android

import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.method.ScrollingMovementMethod
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.cardview.widget.CardView
import com.google.android.material.button.MaterialButton
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * FlowCore Android v1.10 — cliente do FlowCore Core (Termux / PC).
 * Abas: Radar (Macro Score + Regime) | Agente (chat LLM local-first) | Notas | Status
 * Visual: Material 3 dark — header em gradiente, tabs em chips fixas, cartões elevados.
 */
class MainActivity : AppCompatActivity() {

    private val executor = Executors.newSingleThreadExecutor()

    /** Base URL do Core. Editável na aba Status e na tela de primeiro uso.
     *  Default: http://127.0.0.1:8080 (FlowCore no Termux). */
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
    private val C_ON_ACCENT = Color.parseColor("#06141F")
    private val C_CARD = Color.parseColor("#1A2235")
    private val C_CODE = Color.parseColor("#111827")

    private lateinit var root: LinearLayout
    private lateinit var tabsRow: LinearLayout
    private lateinit var content: LinearLayout
    private var currentTab = "radar"
    private var bodyBuilt = false

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
            if (!hasConnection()) {
                requestConnection()
            }
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

    /** O Core ainda nunca respondeu nada (primeira conexão). */
    private fun hasConnection(): Boolean =
        getSharedPreferences("flowcore", 0).getBoolean("connected", false)

    private fun setConnected() =
        getSharedPreferences("flowcore", 0).edit().putBoolean("connected", true).apply()

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

    /* ── Tabs como chips Material (adicionadas UMA única vez) ── */
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
                val radius = 24f
                background = GradientDrawable().apply {
                    shape = GradientDrawable.RECTANGLE
                    cornerRadius = radius
                    setColor(if (key == currentTab) C_ACCENT else C_CARD)
                }
                setTextColor(if (key == currentTab) C_ON_ACCENT else C_SECONDARY)
                layoutParams = LinearLayout.LayoutParams(0, 120).apply {
                    weight = 1f
                    marginStart = if (idx == 0) 0 else 12
                    marginEnd = if (idx == entries.size - 1) 0 else 0
                }
                setOnClickListener { currentTab = key; paintTabs(); showTab(key) }
            }
            tabsRow.addView(btn)
        }
        root.addView(tabsRow)

        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 8, 36, 40)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
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

    /** Apenas repinta o estado selecionado dos chips — não recria nada. */
    private fun paintTabs() {
        val entries = listOf("radar" to "Radar", "agente" to "Agente", "notas" to "Notas", "status" to "Status")
        for (i in 0 until tabsRow.childCount) {
            val btn = tabsRow.getChildAt(i) as MaterialButton
            val (key, _) = entries[i]
            val selected = key == currentTab
            btn.background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = 24f
                setColor(if (selected) C_ACCENT else C_CARD)
            }
            btn.setTextColor(if (selected) C_ON_ACCENT else C_SECONDARY)
        }
    }

    /* ── Conteúdo das abas ───────────────────────────────── */
    private fun showTab(tab: String) {
        content.removeAllViews()
        when (tab) {
            "radar" -> {
                content.addView(sectionTitle("Macro Score · Regime de Mercado"))
                content.addView(actionButton("Atualizar scores") { get("/api/macro-score/scores", it as TextView) })
                content.addView(actionButton("Dimensões") { get("/api/macro-score/dimensions", it as TextView) })
                content.addView(actionButton("Sinais de regime") { get("/api/regime/signals", it as TextView) })
                content.addView(actionButton("Observer (eventos)") { get("/api/observer/events", it as TextView) })
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
                        setColor(C_CODE)
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
                        setColor(C_CARD)
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
                content.addView(actionButton("Listar notas") { get("/api/notes", it as TextView) })
                content.addView(actionButton("Memórias") { get("/api/memories", it as TextView) })
                content.addView(out())
            }
            "status" -> {
                content.addView(sectionTitle("Status do Core e Integrações"))
                content.addView(actionButton("Health") { get("/api/health", it as TextView) })
                content.addView(actionButton("Status completo") { get("/api/status", it as TextView) })
                content.addView(actionButton("Integrações") { get("/api/integrations/status", it as TextView) })
                content.addView(actionButton("LLM Router") { get("/api/llm/status", it as TextView) })
                content.addView(actionButton("WhatsApp") { get("/api/whatsapp/status", it as TextView) })
                content.addView(actionButton("Telegram") { get("/api/telegram/config", it as TextView) })
                content.addView(out())
                content.addView(sectionTitle("Conexão com o Core"))
                content.addView(connectionBox())
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

    private fun actionButton(label: String, onClick: (View) -> Unit): MaterialButton {
        return MaterialButton(this).apply {
            text = label
            tag = label
            textSize = 13f
            isSingleLine = true
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                150
            ).apply { topMargin = 12 }
            setTextColor(C_PRIMARY)
            background = GradientDrawable().apply {
                setColor(C_CARD)
                cornerRadius = 18f
            }
            setOnClickListener(onClick)
        }
    }

    private fun out(): TextView = TextView(this).apply {
        textSize = 12f
        setTextColor(C_PRIMARY)
        setPadding(24, 24, 24, 24)
        background = GradientDrawable().apply {
            setColor(C_CODE)
            cornerRadius = 24f
        }
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = 20 }
        tag = "out"
        text = "Toque em um botão para consultar o Core…"
    }

    private fun connectionBox(): View {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = 12 }
        }
        val hint = TextView(this).apply {
            text = "Conectando ao Core em: $baseUrl"
            textSize = 11f
            setTextColor(C_SECONDARY)
            setPadding(0, 0, 0, 12)
        }
        val urlRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        val urlEt = EditText(this).apply {
            setText(baseUrl)
            setHint("http://127.0.0.1:8080")
            textSize = 12f
            setTextColor(C_PRIMARY)
            setHintTextColor(C_SECONDARY)
            isSingleLine = true
            val lp = LinearLayout.LayoutParams(0, 120)
            lp.weight = 1f
            lp.marginEnd = 16
            layoutParams = lp
            background = GradientDrawable().apply {
                setColor(C_CARD)
                cornerRadius = 18f
            }
        }
        val save = MaterialButton(this).apply {
            text = "Salvar URL"
            textSize = 11f
            isSingleLine = true
            layoutParams = LinearLayout.LayoutParams(240, 120)
            setTextColor(C_ON_ACCENT)
            background = GradientDrawable().apply {
                setColor(C_ACCENT)
                cornerRadius = 24f
            }
            setOnClickListener {
                val u = urlEt.text.toString().trim().trimEnd('/')
                if (u.isNotEmpty()) {
                    baseUrl = u
                    Toast.makeText(this@MainActivity, "URL salva: $u", Toast.LENGTH_SHORT).show()
                    showTab("status")
                }
            }
        }
        urlRow.addView(urlEt)
        urlRow.addView(save)
        val test = MaterialButton(this).apply {
            text = "Testar conexão"
            textSize = 11f
            isSingleLine = true
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                120
            ).apply { topMargin = 12 }
            setTextColor(C_ON_ACCENT)
            background = GradientDrawable().apply {
                setColor(C_VIOLET)
                cornerRadius = 24f
            }
            setOnClickListener {
                requestHealth()
            }
        }
        box.addView(hint)
        box.addView(urlRow)
        box.addView(test)
        return box
    }

    /** Tela de primeiro uso: pergunta a URL do Core antes de qualquer consulta. */
    private fun requestConnection() {
        val card = CardView(this).apply {
            radius = 28f
            cardElevation = 0f
            setCardBackgroundColor(C_CARD)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        val inner = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 48, 40, 48)
        }
        inner.addView(TextView(this).apply {
            text = "CONFIGURAR CONEXÃO"
            textSize = 13f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(C_ACCENT)
            letterSpacing = 0.08f
        })
        inner.addView(TextView(this).apply {
            text = "Informe o endereço do FlowCore Core.\nNo Termux: http://127.0.0.1:8080\nNa LAN (PC): http://IP_DO_PC:8090"
            textSize = 13f
            setTextColor(C_SECONDARY)
            setPadding(0, 20, 0, 28)
        })
        val urlEt = EditText(this).apply {
            setText(baseUrl)
            textSize = 14f
            setTextColor(C_PRIMARY)
            setHintTextColor(C_SECONDARY)
            isSingleLine = true
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                130
            )
            background = GradientDrawable().apply {
                setColor(C_CODE)
                cornerRadius = 20f
            }
        }
        val btn = MaterialButton(this).apply {
            text = "Conectar"
            isSingleLine = true
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                140
            ).apply { topMargin = 24 }
            setTextColor(C_ON_ACCENT)
            background = GradientDrawable().apply {
                setColor(C_ACCENT)
                cornerRadius = 24f
            }
            setOnClickListener {
                val u = urlEt.text.toString().trim().trimEnd('/')
                if (u.isNotEmpty()) {
                    baseUrl = u
                    setConnected()
                    root.removeView(card)
                    Toast.makeText(this@MainActivity, "Conectando em $u…", Toast.LENGTH_SHORT).show()
                    requestHealth()
                }
            }
        }
        inner.addView(urlEt)
        inner.addView(btn)
        card.addView(inner)
        content.addView(card)
    }

    /** GET simples: marca o botão clicado com "…" e exibe o resultado no bloco de saída, marcando conectado em caso de sucesso. */
    private fun get(endpoint: String, clicked: View) {
        (clicked as? MaterialButton)?.text = "…"
        val display = findOutTextView()
        display?.text = "GET $endpoint…"
        executor.execute {
            val result = request("GET", endpoint, null)
            runOnUiThread {
                (clicked as? MaterialButton)?.text = clicked.tag as? String ?: ""
                display?.text = formatJson(result)
                if (!result.startsWith("HTTP") && !result.contains("Exception") && !result.contains("ConnectException")) {
                    setConnected()
                }
            }
        }
    }
    private fun findOutTextView(): TextView? {
        val stack = java.util.ArrayDeque<View>()
        stack.add(root)
        while (stack.isNotEmpty()) {
            val v = stack.pop()
            if (v is TextView && v.tag == "out") return v
            if (v is ViewGroup) for (i in 0 until v.childCount) stack.add(v.getChildAt(i))
        }
        return null
    }

    /** Health sem alvo de exibição — usado pelo botão "Testar conexão". */
    private fun requestHealth() {
        executor.execute {
            val result = request("GET", "/api/health", null)
            runOnUiThread {
                if (!result.startsWith("HTTP") && !result.contains("Exception") && !result.contains("ConnectException")) {
                    setConnected()
                    Toast.makeText(this, "Conectado ao Core em $baseUrl", Toast.LENGTH_SHORT).show()
                } else {
                    val hint = if (result.contains("ConnectException") || result.contains("SocketTimeoutException")) {
                        "Não alcançou $baseUrl.\nVerifique: mesmo Wi-Fi do PC (não 5G) e firewall."
                    } else { result }
                    Toast.makeText(this, "Falha: $hint", Toast.LENGTH_LONG).show()
                }
            }
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
                setConnected()
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
            connection.connectTimeout = 15000
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

package com.flowcore.android

import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var output: TextView
    private lateinit var serverUrlInput: EditText
    private val preferences by lazy {
        getSharedPreferences("flowcore_settings", Context.MODE_PRIVATE)
    }

    private data class Check(
        val buttonId: Int,
        val label: String,
        val path: String,
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        output = findViewById(R.id.outputText)
        serverUrlInput = findViewById(R.id.serverUrlInput)

        val savedUrl = preferences.getString(KEY_BASE_URL, BuildConfig.FLOWCORE_BASE_URL)
            ?: BuildConfig.FLOWCORE_BASE_URL
        serverUrlInput.setText(savedUrl)

        findViewById<Button>(R.id.termuxButton).setOnClickListener {
            setPreset("http://127.0.0.1:8080")
        }
        findViewById<Button>(R.id.emulatorButton).setOnClickListener {
            setPreset("http://10.0.2.2:8080")
        }
        findViewById<Button>(R.id.lanButton).setOnClickListener {
            serverUrlInput.requestFocus()
            serverUrlInput.setSelection(serverUrlInput.text.length)
            output.text = "Digite o IP do computador na rede local.\nExemplo: http://192.168.1.50:8080"
        }
        findViewById<Button>(R.id.saveServerButton).setOnClickListener {
            saveServerUrl(showMessage = true)
        }
        findViewById<Button>(R.id.testConnectionButton).setOnClickListener {
            runCheck("Teste de conexão", "/api/health")
        }

        val checks = listOf(
            Check(R.id.statusButton, "Status", "/api/status"),
            Check(R.id.doctorButton, "Diagnóstico", "/api/status"),
            Check(R.id.batteryButton, "Sistema / bateria", "/api/system"),
            Check(R.id.wifiButton, "Sistema / Wi-Fi", "/api/system"),
            Check(R.id.storageButton, "Sistema / armazenamento", "/api/system"),
            Check(R.id.runtimeButton, "Health da API", "/api/health"),
            Check(R.id.passportButton, "Passport", "/api/passport"),
        )
        checks.forEach { check ->
            findViewById<Button>(check.buttonId).setOnClickListener {
                runCheck(check.label, check.path)
            }
        }

        output.text = "Servidor configurado em:\n${normalizeBaseUrl(savedUrl)}\n\nToque em TESTAR CONEXÃO."
    }

    private fun setPreset(url: String) {
        serverUrlInput.setText(url)
        saveServerUrl(showMessage = false)
        output.text = "Endereço selecionado:\n$url\n\nToque em TESTAR CONEXÃO."
    }

    private fun saveServerUrl(showMessage: Boolean): String? {
        val normalized = normalizeBaseUrl(serverUrlInput.text.toString())
        if (normalized == null) {
            output.text = "Endereço inválido. Use, por exemplo:\nhttp://192.168.1.50:8080"
            return null
        }
        serverUrlInput.setText(normalized)
        serverUrlInput.setSelection(serverUrlInput.text.length)
        preferences.edit().putString(KEY_BASE_URL, normalized).apply()
        if (showMessage) {
            output.text = "Endereço salvo:\n$normalized\n\nToque em TESTAR CONEXÃO."
        }
        return normalized
    }

    private fun runCheck(label: String, path: String) {
        val baseUrl = saveServerUrl(showMessage = false) ?: return
        output.text = "$label\nGET $baseUrl$path ..."
        executor.execute {
            val result = request(baseUrl, path)
            runOnUiThread { output.text = result }
        }
    }

    private fun request(baseUrl: String, path: String): String {
        val connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection)
        return try {
            connection.requestMethod = "GET"
            connection.connectTimeout = 5000
            connection.readTimeout = 10000
            connection.setRequestProperty("Accept", "application/json")

            val statusCode = connection.responseCode
            val stream = if (statusCode in 200..299) {
                connection.inputStream
            } else {
                connection.errorStream
            }
            val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (statusCode in 200..299) {
                "Conexão OK · HTTP $statusCode\n$baseUrl$path\n\n$body"
            } else {
                "HTTP $statusCode\n$baseUrl$path\n\n$body"
            }
        } catch (error: Exception) {
            "Falha ao conectar em $baseUrl\n" +
                "${error::class.java.simpleName}: ${error.message ?: error}\n\n" +
                connectionHint(baseUrl)
        } finally {
            connection.disconnect()
        }
    }

    private fun connectionHint(baseUrl: String): String {
        return when {
            baseUrl.contains("127.0.0.1") || baseUrl.contains("localhost") ->
                "Dica: esse endereço aponta para o próprio celular. Use Termux no celular ou informe o IP do PC na rede."
            else ->
                "Dica: confirme que o FlowCore está ativo, escutando na rede local, e que a porta 8080 não está bloqueada pelo firewall."
        }
    }

    private fun normalizeBaseUrl(raw: String): String? {
        var value = raw.trim().trimEnd('/')
        if (value.isEmpty()) return null
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "http://$value"
        }
        val uri = Uri.parse(value)
        if (uri.host.isNullOrBlank()) return null
        return value
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }

    companion object {
        private const val KEY_BASE_URL = "base_url"
    }
}

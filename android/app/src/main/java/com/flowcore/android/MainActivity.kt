package com.flowcore.android

import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var output: TextView

    private data class Check(
        val buttonId: Int,
        val label: String,
        val path: String,
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        output = findViewById(R.id.outputText)

        val checks = listOf(
            Check(R.id.statusButton, "Status", "/api/status"),
            Check(R.id.doctorButton, "Diagnóstico", "/api/status"),
            Check(R.id.batteryButton, "Sistema / bateria", "/api/system"),
            Check(R.id.wifiButton, "Sistema / Wi-Fi", "/api/system"),
            Check(R.id.storageButton, "Sistema / armazenamento", "/api/system"),
            Check(R.id.runtimeButton, "Health da API", "/api/health"),
            Check(R.id.passportButton, "Passport", "/api/passport"),
        )

        checks.forEach { check -> bind(check.buttonId, check.label, check.path) }
        output.text = "Servidor configurado em:\n${BuildConfig.FLOWCORE_BASE_URL}\n\nSelecione uma verificação."
    }

    private fun bind(buttonId: Int, label: String, path: String) {
        findViewById<Button>(buttonId).setOnClickListener {
            output.text = "$label\nGET $path ..."
            executor.execute {
                val result = request(path)
                runOnUiThread { output.text = result }
            }
        }
    }

    private fun request(path: String): String {
        val baseUrl = BuildConfig.FLOWCORE_BASE_URL.trimEnd('/')
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
                body
            } else {
                "HTTP $statusCode\n$body"
            }
        } catch (error: Exception) {
            "Falha ao conectar em $baseUrl\n" +
                "${error::class.java.simpleName}: ${error.message ?: error}"
        } finally {
            connection.disconnect()
        }
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }
}

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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        output = findViewById(R.id.outputText)

        bind(R.id.statusButton, "status")
        bind(R.id.doctorButton, "doctor")
        bind(R.id.batteryButton, "battery")
        bind(R.id.wifiButton, "wifi")
        bind(R.id.storageButton, "storage")
        bind(R.id.runtimeButton, "runtime")
        bind(R.id.passportButton, "passport")
    }

    private fun bind(buttonId: Int, endpoint: String) {
        findViewById<Button>(buttonId).setOnClickListener {
            output.text = "GET /$endpoint ..."
            executor.execute {
                val result = request(endpoint)
                runOnUiThread { output.text = result }
            }
        }
    }

    private fun request(endpoint: String): String {
        val connection = (URL("http://127.0.0.1:8000/$endpoint")
            .openConnection() as HttpURLConnection)
        return try {
            connection.requestMethod = "GET"
            connection.connectTimeout = 5000
            connection.readTimeout = 10000
            val stream = if (connection.responseCode >= 400) {
                connection.errorStream
            } else {
                connection.inputStream
            }
            val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (connection.responseCode >= 400) {
                "HTTP ${connection.responseCode}: $body"
            } else {
                body
            }
        } catch (error: Exception) {
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

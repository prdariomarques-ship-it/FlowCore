plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.flowcore.android"
    compileSdk = 35

    kotlinOptions {
        jvmTarget = "17"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }

    defaultConfig {
        applicationId = "com.flowcore.android"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        // Termux no mesmo aparelho. Para emulador use http://10.0.2.2:8080;
        // para outro dispositivo use http://<ip-da-maquina>:8080.
        buildConfigField("String", "FLOWCORE_BASE_URL", "\"http://127.0.0.1:8080\"")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
}

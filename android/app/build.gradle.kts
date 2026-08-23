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

    defaultConfig {
        applicationId = "com.flowcore.android"
        minSdk = 24
        targetSdk = 35
        versionCode = 15
        versionName = "1.15"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
        debug {
            // usa o keystore de debug padrão do Android (~/.android/debug.keystore)
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
}

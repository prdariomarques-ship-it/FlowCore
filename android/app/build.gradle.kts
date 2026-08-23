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

    signingConfigs {
        getByName("debug") {
            val ks = rootProject.file("flowcore-debug.keystore")
            storeFile = if (ks.exists()) ks else null
            storePassword = "android"
            keyAlias = "flowcore"
            keyPassword = "android"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
        debug {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
}

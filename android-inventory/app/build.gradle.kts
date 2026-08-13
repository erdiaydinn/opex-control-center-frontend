plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.opex.inventory"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.opex.inventory"
        minSdk = 26
        targetSdk = 35
        versionCode = 24
        versionName = "24.0.0"
        buildConfigField(
            "String",
            "API_BASE_URL",
            "\"${project.findProperty("OPEX_API_BASE_URL") ?: "https://inventory.company.com"}\""
        )
    }

    buildFeatures { buildConfig = true }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
}

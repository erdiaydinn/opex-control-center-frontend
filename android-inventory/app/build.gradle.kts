plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.devtools.ksp")
}

fun env(name: String, fallback: String = ""): String = System.getenv(name) ?: fallback
fun quoted(value: String): String = "\"${value.replace("\\", "\\\\").replace("\"", "\\\"")}\""

android {
    namespace = "com.eay.inventory"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.eay.inventory"
        minSdk = 26
        targetSdk = 35
        versionCode = 300001
        versionName = "30.0.1-p0"
        manifestPlaceholders["appAuthRedirectScheme"] = "com.eay.inventory"
        buildConfigField("String", "API_BASE_URL", quoted(env("EAY_API_BASE_URL", "https://invalid.eay.example")))
        buildConfigField("String", "OIDC_ISSUER", quoted(env("EAY_OIDC_ISSUER", "https://invalid.eay.example")))
        buildConfigField("String", "OIDC_CLIENT_ID", quoted(env("EAY_OIDC_CLIENT_ID", "unset")))
        buildConfigField("String", "TLS_PIN_PRIMARY", quoted(env("EAY_TLS_PIN_PRIMARY", "sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")))
        buildConfigField("String", "TLS_PIN_BACKUP", quoted(env("EAY_TLS_PIN_BACKUP", "sha256/BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=")))
    }

    buildFeatures { buildConfig = true }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = if (env("EAY_KEYSTORE_FILE").isNotBlank()) signingConfigs.create("managedRelease") {
                storeFile = file(env("EAY_KEYSTORE_FILE"))
                storePassword = env("EAY_ANDROID_STORE_PASSWORD")
                keyAlias = env("EAY_ANDROID_KEY_ALIAS")
                keyPassword = env("EAY_ANDROID_KEY_PASSWORD")
                enableV1Signing = false
                enableV2Signing = true
                enableV3Signing = true
                enableV4Signing = true
            } else null
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
    implementation("androidx.room:room-runtime:2.7.1")
    implementation("androidx.room:room-ktx:2.7.1")
    ksp("androidx.room:room-compiler:2.7.1")
    implementation("androidx.work:work-runtime-ktx:2.11.2")
    implementation("androidx.sqlite:sqlite:2.5.1")
    implementation("net.zetetic:sqlcipher-android:4.17.0")
    implementation("net.openid:appauth:0.11.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("junit:junit:4.13.2")
}

ksp {
    arg("room.schemaLocation", "$projectDir/schemas")
}

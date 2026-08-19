plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.eay.mobile.fieldui"
    compileSdk = 35

    defaultConfig {
        minSdk = 26
    }

    buildFeatures {
        compose = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    sourceSets.getByName("main") {
        java.srcDir(rootProject.projectDir.parentFile.resolve("android-field-ui/field-ui/src/main/java"))
        res.srcDir(rootProject.projectDir.parentFile.resolve("android-field-ui/field-ui/src/main/res"))
    }
}

dependencies {
    api(project(":mobile-presentation-contracts"))

    // Production Inventory remains on AGP 8.7.x. Keep this compatibility build on the
    // Compose 1.8.x line so Android Lint and the Kotlin analysis API stay binary-compatible.
    // The standalone android-field-ui build remains the forward/latest compatibility gate.
    // Compose UI is part of this module's public ABI because EayTerminalRuntimeView publicly
    // extends AbstractComposeView; consumers must see that supertype on their compile classpath.
    api(platform("androidx.compose:compose-bom:2025.06.01"))
    api("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")

    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
}

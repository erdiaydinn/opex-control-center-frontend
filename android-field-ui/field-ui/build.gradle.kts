plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.eay.mobile.fieldui"
    compileSdk = 37

    defaultConfig {
        minSdk = 26
        consumerProguardFiles("consumer-rules.pro")
    }

    buildFeatures {
        compose = true
    }

    lint {
        abortOnError = true
        warningsAsErrors = true
        checkReleaseBuilds = true
        // Dependency freshness is governed by Repository Intelligence + exact pin review.
        // Treating "a newer version exists" as a build failure would conflict with that policy.
        disable += setOf("GradleDependency", "NewerVersionAvailable")
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.06.00")
    val cameraXVersion = "1.6.1"

    implementation(project(":mobile-presentation-contracts"))
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")

    implementation("androidx.camera:camera-core:$cameraXVersion")
    implementation("androidx.camera:camera-camera2:$cameraXVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraXVersion")
    implementation("androidx.camera:camera-view:$cameraXVersion")
    implementation("androidx.camera:camera-video:$cameraXVersion")

    // Reviewed upstream sample currently uses tasks-vision 1.0.0.
    // Model assets remain separately governed/fingerprinted; no runtime download is allowed.
    implementation("com.google.mediapipe:tasks-vision:1.0.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
}

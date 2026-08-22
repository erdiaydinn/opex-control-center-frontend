plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.eay.mobile.presentation.adapter"
    compileSdk = 35

    defaultConfig {
        minSdk = 26
        consumerProguardFiles("consumer-rules.pro")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    lint {
        abortOnError = true
        warningsAsErrors = true
        checkReleaseBuilds = true
    }
}

dependencies {
    implementation(project(":mobile-core"))
    api(project(":mobile-presentation-contracts"))
    testImplementation("junit:junit:4.13.2")
}

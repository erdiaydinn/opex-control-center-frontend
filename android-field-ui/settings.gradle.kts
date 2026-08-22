pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "EayFieldUiCompatibility"
include(":mobile-presentation-contracts")
project(":mobile-presentation-contracts").projectDir = file("../mobile-presentation-contracts")
include(":field-ui")

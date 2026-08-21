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

rootProject.name = "EayInventory"
include(":mobile-presentation-contracts")
project(":mobile-presentation-contracts").projectDir = file("../mobile-presentation-contracts")
include(":mobile-core")
include(":field-presentation-adapter")
include(":field-ui-runtime")
include(":app")
include(":eay-one-app")

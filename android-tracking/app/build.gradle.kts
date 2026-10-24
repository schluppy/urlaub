plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "de.urlaubsplaner.tracking"
    compileSdk = 35
    buildToolsVersion = "35.0.0"

    defaultConfig {
        applicationId = "de.urlaubsplaner.tracking"
        minSdk = 33
        targetSdk = 35
        versionCode = 2
        versionName = "0.2"
    }

    // Derselbe feste Schlüssel wie beim Handy-Widget (siehe bauen.sh), damit Updates
    // sich über die installierte App spielen lassen.
    signingConfigs {
        create("release") {
            storeFile = System.getenv("SIGNIER_DATEI")?.let { file(it) }
            storePassword = System.getenv("SIGNIER_PASSWORT")
            keyAlias = "urlaubswidget"
            keyPassword = System.getenv("SIGNIER_PASSWORT")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}

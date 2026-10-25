plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "de.urlaubsplaner.widget"
    compileSdk = 35
    buildToolsVersion = "35.0.0"

    defaultConfig {
        applicationId = "de.urlaubsplaner.widget"
        minSdk = 29
        targetSdk = 35
        versionCode = 5
        versionName = "1.4"
    }

    // Signiert wird mit einem festen Schlüssel außerhalb des Repositorys (siehe bauen.sh),
    // sonst lässt sich eine neue Version nicht über die alte installieren.
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

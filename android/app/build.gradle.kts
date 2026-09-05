import org.gradle.api.GradleException

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.devtools.ksp")
}

fun environmentValue(name: String): String? = providers.environmentVariable(name).orNull
    ?.trim()
    ?.takeIf { it.isNotEmpty() }

fun quotedBuildConfig(value: String): String = "\"${value.replace("\\", "\\\\").replace("\"", "\\\"")}\""

fun normalizedHttpsBaseUrl(raw: String): String {
    val value = raw.trim()
    if (!value.startsWith("https://", ignoreCase = true)) {
        throw GradleException("CEH_ANDROID_API_BASE_URL для release должен начинаться с https://")
    }
    return if (value.endsWith("/")) value else "$value/"
}

fun positiveVersionCode(): Int {
    val raw = environmentValue("CEH_ANDROID_VERSION_CODE") ?: return 1
    return raw.toIntOrNull()?.takeIf { it > 0 }
        ?: throw GradleException("CEH_ANDROID_VERSION_CODE должен быть положительным целым числом")
}

val releaseRequested = gradle.startParameter.taskNames.any {
    it.contains("release", ignoreCase = true)
}
val releaseApiBaseUrl = environmentValue("CEH_ANDROID_API_BASE_URL")?.let(::normalizedHttpsBaseUrl)
    ?: if (releaseRequested) {
        throw GradleException("Для release-сборки задайте CEH_ANDROID_API_BASE_URL с HTTPS-адресом backend")
    } else {
        "https://example.invalid/"
    }

val signingEnvironment = mapOf(
    "CEH_ANDROID_KEYSTORE_FILE" to environmentValue("CEH_ANDROID_KEYSTORE_FILE"),
    "CEH_ANDROID_KEYSTORE_PASSWORD" to environmentValue("CEH_ANDROID_KEYSTORE_PASSWORD"),
    "CEH_ANDROID_KEY_ALIAS" to environmentValue("CEH_ANDROID_KEY_ALIAS"),
    "CEH_ANDROID_KEY_PASSWORD" to environmentValue("CEH_ANDROID_KEY_PASSWORD"),
)
val missingSigningEnvironment = signingEnvironment.filterValues { it == null }.keys
if (releaseRequested && missingSigningEnvironment.isNotEmpty()) {
    throw GradleException(
        "Для release-сборки не заданы параметры подписи: ${missingSigningEnvironment.joinToString()}",
    )
}
val releaseSigningConfigured = missingSigningEnvironment.isEmpty()

android {
    namespace = "ru.ceh.sklad"
    compileSdk = 37

    defaultConfig {
        applicationId = "ru.ceh.sklad"
        minSdk = 26
        targetSdk = 37
        versionCode = positiveVersionCode()
        versionName = environmentValue("CEH_ANDROID_VERSION_NAME") ?: "0.1.0"
    }

    signingConfigs {
        if (releaseSigningConfigured) {
            create("release") {
                storeFile = file(signingEnvironment.getValue("CEH_ANDROID_KEYSTORE_FILE")!!)
                storePassword = signingEnvironment.getValue("CEH_ANDROID_KEYSTORE_PASSWORD")!!
                keyAlias = signingEnvironment.getValue("CEH_ANDROID_KEY_ALIAS")!!
                keyPassword = signingEnvironment.getValue("CEH_ANDROID_KEY_PASSWORD")!!
            }
        }
    }

    buildTypes {
        getByName("debug") {
            buildConfigField("String", "API_BASE_URL", quotedBuildConfig("http://10.0.2.2:8000/"))
        }
        getByName("release") {
            buildConfigField("String", "API_BASE_URL", quotedBuildConfig(releaseApiBaseUrl))
            if (releaseSigningConfigured) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.08.00")
    implementation(composeBom)

    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.11.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.11.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.11.0")

    val roomVersion = "3.0.2"
    implementation("androidx.room3:room3-runtime:$roomVersion")
    ksp("androidx.room3:room3-compiler:$roomVersion")

    implementation("androidx.work:work-runtime-ktx:2.11.2")

    implementation("com.squareup.retrofit2:retrofit:3.0.0")
    implementation("com.squareup.retrofit2:converter-gson:3.0.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
}

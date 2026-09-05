# Android instrumented smoke

Ручной workflow `Android инструментальные smoke-тесты` запускает `connectedDebugAndroidTest` на Android 35 Emulator. Тест не требует production keystore и не выполняет реальные складские операции.

## Диагностика

Независимо от результата теста workflow сохраняет artifact `ceh-sklad-android-smoke`:

- JUnit/androidTest results;
- HTML report Android instrumentation;
- `android-smoke-logcat.txt`;
- финальный screenshot эмулятора;
- `dumpsys package ru.ceh.sklad`.

Logcat и screenshot снимаются **до остановки emulator-runner**, поэтому они доступны и при падении Gradle/instrumentation.

Artifact хранится 14 дней. Debug smoke не содержит release keystore/signing secrets.

## Критерий release-приемки

Перед выводом PR из draft нужен фактический успешный ручной запуск workflow и просмотр artifact. Отдельно на целевом устройстве проверяется подписанный APK из `Подписанный Android release`.

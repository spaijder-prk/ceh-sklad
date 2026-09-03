package ru.ceh.sklad.data

fun isMobileRepresentative(user: UserInfo?): Boolean =
    user?.role == "representative" && !user.location_id.isNullOrBlank()

fun requireMobileRepresentative(user: UserInfo): UserInfo {
    if (!isMobileRepresentative(user)) {
        throw MobileSessionRejectedException(
            "Android-приложение предназначено только для торгового представителя с привязанным виртуальным складом."
        )
    }
    return user
}

class MobileSessionRejectedException(message: String) : IllegalStateException(message)

package com.betguard.filter

import android.content.Context

/** Small UI preferences stay separate from the existing Room rules/history schema. */
object AppearancePreferences {
    private const val FILE = "betguard_appearance"
    fun read(context: Context): String =
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString("theme", "system") ?: "system"

    fun save(context: Context, mode: String) {
        require(mode in listOf("system", "light", "dark")) { "Choose system, light or dark appearance." }
        check(context.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit().putString("theme", mode).commit()) {
            "Could not save appearance."
        }
    }
}

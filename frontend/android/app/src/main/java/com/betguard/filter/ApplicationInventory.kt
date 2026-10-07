package com.betguard.filter

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import org.json.JSONArray
import org.json.JSONObject

/** Local, explicit inventory of visible launchable apps. No usage or network upload. */
object ApplicationInventory {
    @Suppress("DEPRECATION")
    fun read(context: Context): String {
        val manager = context.packageManager
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val applications = manager.queryIntentActivities(intent, 0)
            .map { it.activityInfo.applicationInfo }
            .distinctBy { it.packageName }
            .filter { it.packageName != context.packageName }
            .sortedBy { manager.getApplicationLabel(it).toString().lowercase() }
            .take(500)
        val rows = JSONArray()
        for (application in applications) {
            // An app can be uninstalled between querying and reading metadata.
            try {
                val info = manager.getPackageInfo(application.packageName, PackageManager.GET_PERMISSIONS)
                rows.put(JSONObject()
                    .put("app_name", manager.getApplicationLabel(application).toString().take(200))
                    .put("package_name", application.packageName)
                    .put("permissions", JSONArray((info.requestedPermissions ?: emptyArray())
                        .map { it.take(160) }.distinct().sorted().take(150))))
            } catch (_: PackageManager.NameNotFoundException) { /* Ignore a removed app. */ }
        }
        return rows.toString()
    }
}

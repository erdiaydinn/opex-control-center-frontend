package com.eay.inventory

import android.content.Context
import android.content.Intent
import android.os.Bundle

object DataWedge {
    const val SCAN_ACTION = "com.eay.inventory.SCAN"

    fun configure(context: Context) {
        val profile = Bundle().apply {
            putString("PROFILE_NAME", "EAY_INVENTORY_PRODUCTION")
            putString("PROFILE_ENABLED", "true")
            putString("CONFIG_MODE", "CREATE_IF_NOT_EXIST")
            putParcelableArray("APP_LIST", arrayOf(Bundle().apply {
                putString("PACKAGE_NAME", context.packageName)
                putStringArray("ACTIVITY_LIST", arrayOf("*"))
            }))
            putBundle("PLUGIN_CONFIG", Bundle().apply {
                putString("PLUGIN_NAME", "INTENT")
                putString("RESET_CONFIG", "true")
                putBundle("PARAM_LIST", Bundle().apply {
                    putString("intent_output_enabled", "true")
                    putString("intent_action", SCAN_ACTION)
                    putString("intent_delivery", "2")
                    putString("intent_component_info", context.packageName)
                })
            })
        }
        context.sendBroadcast(Intent("com.symbol.datawedge.api.ACTION").apply {
            setPackage("com.symbol.datawedge")
            putExtra("com.symbol.datawedge.api.SET_CONFIG", profile)
        })
    }
}

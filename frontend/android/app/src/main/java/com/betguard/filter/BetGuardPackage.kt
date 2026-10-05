package com.betguard.filter

import com.facebook.react.BaseReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.module.model.ReactModuleInfo
import com.facebook.react.module.model.ReactModuleInfoProvider

class BetGuardPackage : BaseReactPackage() {
    override fun getModule(name: String, context: ReactApplicationContext): NativeModule? =
        if (name == BetGuardModule.NAME) BetGuardModule(context) else null
    override fun getReactModuleInfoProvider() = ReactModuleInfoProvider {
        mapOf(BetGuardModule.NAME to ReactModuleInfo(
            BetGuardModule.NAME, BetGuardModule.NAME, false, false, false, true
        ))
    }
}

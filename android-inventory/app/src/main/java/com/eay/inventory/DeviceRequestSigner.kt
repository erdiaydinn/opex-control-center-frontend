package com.eay.inventory

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.Signature
import java.util.Base64

object DeviceRequestSigner {
    private const val ALIAS = "eay-inventory-device-proof-v1"

    fun ensureKey() {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (store.containsAlias(ALIAS)) return
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
        generator.initialize(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setAlgorithmParameterSpec(java.security.spec.ECGenParameterSpec("secp256r1"))
                .setUserAuthenticationRequired(false)
                .build(),
        )
        generator.generateKeyPair()
    }

    fun sign(message: ByteArray): String {
        ensureKey()
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val key = store.getKey(ALIAS, null) as java.security.PrivateKey
        val signature = Signature.getInstance("SHA256withECDSA")
        signature.initSign(key)
        signature.update(message)
        return Base64.getEncoder().encodeToString(signature.sign())
    }

    fun publicKeyPem(): String {
        ensureKey()
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val encoded = Base64.getMimeEncoder(64, "\n".toByteArray()).encodeToString(store.getCertificate(ALIAS).publicKey.encoded)
        return "-----BEGIN PUBLIC KEY-----\n$encoded\n-----END PUBLIC KEY-----"
    }
}

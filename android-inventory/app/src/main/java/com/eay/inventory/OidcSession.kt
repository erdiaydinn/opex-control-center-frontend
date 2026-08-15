package com.eay.inventory

import android.content.Context
import android.content.Intent
import net.openid.appauth.AuthorizationException
import net.openid.appauth.AuthorizationResponse
import net.openid.appauth.AuthorizationService
import kotlinx.coroutines.runBlocking
import java.util.UUID

class OidcSession(context: Context) {
    private val service = AuthorizationService(context)
    private val appContext = context.applicationContext

    fun consumeAuthorizationResponse(intent: Intent, done: (Result<Unit>) -> Unit) {
        val response = AuthorizationResponse.fromIntent(intent)
        val exception = AuthorizationException.fromIntent(intent)
        if (response == null) { done(Result.failure(exception ?: IllegalStateException("OIDC response missing"))); return }
        service.performTokenRequest(response.createTokenExchangeRequest()) { token, error ->
            if (token?.accessToken.isNullOrBlank() || token?.refreshToken.isNullOrBlank()) done(Result.failure(error ?: IllegalStateException("access/refresh token missing")))
            else {
                val authBindingId = UUID.randomUUID().toString()
                AccessTokenMemory.replace(token!!.accessToken!!, token.accessTokenExpirationTime ?: 0L)
                runBlocking {
                    InventoryDatabase.get(appContext).sessions().put(AuthSession(
                        refreshToken = token.refreshToken!!,
                        tokenEndpoint = response.request.configuration.tokenEndpoint.toString(),
                        clientId = response.request.clientId,
                        authBindingId = authBindingId,
                    ))
                }
                done(Result.success(Unit))
            }
            service.dispose()
        }
    }
}

object AccessTokenMemory {
    @Volatile private var token: String? = null
    @Volatile private var expiresAt: Long = 0
    fun replace(value: String, expiry: Long) { token = value; expiresAt = expiry }
    fun requireFresh(): String = token?.takeIf { System.currentTimeMillis() + 30_000 < expiresAt }
        ?: throw IllegalStateException("OIDC access token expired")
    fun freshOrNull(): String? = token?.takeIf { System.currentTimeMillis() + 30_000 < expiresAt }
    fun clear() { token = null; expiresAt = 0 }
}

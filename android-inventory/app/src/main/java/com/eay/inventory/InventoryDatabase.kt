package com.eay.inventory

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import net.zetetic.database.sqlcipher.SupportOpenHelperFactory
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

@Entity(
    tableName = "offline_events",
    indices = [
        Index(value = ["eventId"], unique = true),
        Index(value = ["deviceSequence"], unique = true),
        Index(value = ["state", "nextAttemptAt"]),
    ],
)
data class OfflineEvent(
    @PrimaryKey val eventId: String,
    val deviceSequence: Long,
    val canonicalPayload: String,
    val payloadHash: String,
    val authBindingId: String = "",
    val state: String = "PENDING",
    val attempts: Int = 0,
    val nextAttemptAt: Long = 0,
    val createdAt: Long = System.currentTimeMillis(),
    val quarantineReason: String? = null,
    val lastServerCode: String? = null,
    val recoveryCaseId: String? = null,
    val recoveryState: String? = null,
)

@Entity(tableName = "auth_session")
data class AuthSession(
    @PrimaryKey val id: Int = 1,
    val refreshToken: String,
    val tokenEndpoint: String,
    val clientId: String,
    val authBindingId: String,
)

@Dao
interface OfflineEventDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(event: OfflineEvent)

    @Query("SELECT * FROM offline_events WHERE eventId=:eventId LIMIT 1")
    suspend fun byEventId(eventId: String): OfflineEvent?

    @Query("SELECT * FROM offline_events WHERE deviceSequence=:deviceSequence LIMIT 1")
    suspend fun byDeviceSequence(deviceSequence: Long): OfflineEvent?

    @Query("SELECT COALESCE(MAX(deviceSequence), 0) FROM offline_events")
    suspend fun maxDeviceSequence(): Long

    @Query(
        "SELECT * FROM offline_events " +
            "WHERE state IN ('PENDING','RETRY_WAIT') AND nextAttemptAt<=:now " +
            "ORDER BY deviceSequence LIMIT :limit",
    )
    suspend fun due(now: Long, limit: Int = 100): List<OfflineEvent>

    @Query(
        "SELECT * FROM offline_events " +
            "WHERE deviceSequence<:beforeSequence AND state<>'ACKED' " +
            "ORDER BY deviceSequence",
    )
    suspend fun unsettledBefore(beforeSequence: Long): List<OfflineEvent>

    @Query(
        "SELECT * FROM offline_events " +
            "WHERE state='QUARANTINED' AND recoveryCaseId IS NULL " +
            "ORDER BY deviceSequence LIMIT :limit",
    )
    suspend fun recoveryCandidates(limit: Int = 50): List<OfflineEvent>

    @Query("UPDATE offline_events SET state='ACKED' WHERE eventId=:eventId")
    suspend fun acknowledge(eventId: String)

    @Query(
        "UPDATE offline_events SET state='ACKED', quarantineReason=NULL, " +
            "lastServerCode=:serverCode, nextAttemptAt=0 WHERE eventId=:eventId",
    )
    suspend fun acknowledgeWithCode(eventId: String, serverCode: String)

    @Query(
        "UPDATE offline_events SET state='RETRY_WAIT', attempts=attempts+1, " +
            "nextAttemptAt=:nextAt WHERE eventId=:eventId",
    )
    suspend fun retry(eventId: String, nextAt: Long)

    @Query(
        "UPDATE offline_events SET state='RETRY_WAIT', attempts=attempts+1, " +
            "nextAttemptAt=:nextAt, quarantineReason=NULL, lastServerCode=:serverCode " +
            "WHERE eventId=:eventId",
    )
    suspend fun retryWithCode(eventId: String, nextAt: Long, serverCode: String)

    @Query(
        "UPDATE offline_events SET state='QUARANTINED', quarantineReason=:reason, " +
            "lastServerCode=:serverCode, nextAttemptAt=0 WHERE eventId=:eventId",
    )
    suspend fun quarantine(eventId: String, reason: String, serverCode: String)

    @Query(
        "UPDATE offline_events SET recoveryCaseId=:caseId, recoveryState='REQUESTED' " +
            "WHERE eventId=:eventId AND state='QUARANTINED' AND recoveryCaseId IS NULL",
    )
    suspend fun markRecoveryRequested(eventId: String, caseId: String): Int

    @Query("SELECT COUNT(*) FROM offline_events WHERE state IN ('PENDING','RETRY_WAIT')")
    suspend fun pendingCount(): Int

    @Query("SELECT COUNT(*) FROM offline_events WHERE state='QUARANTINED'")
    suspend fun quarantinedCount(): Int
}

@Dao
interface AuthSessionDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(session: AuthSession)

    @Query("SELECT * FROM auth_session WHERE id=1")
    suspend fun get(): AuthSession?

    @Query("DELETE FROM auth_session")
    suspend fun clear()
}

@Database(
    entities = [OfflineEvent::class, AuthSession::class],
    version = 5,
    exportSchema = true,
)
abstract class InventoryDatabase : RoomDatabase() {
    abstract fun events(): OfflineEventDao
    abstract fun sessions(): AuthSessionDao

    companion object {
        @Volatile private var instance: InventoryDatabase? = null
        private const val KEY_ALIAS = "eay-inventory-room-key-v1"

        private val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                // Existing queued events predate auth-session binding. They deliberately
                // migrate to an empty binding and therefore cannot be replayed until
                // explicitly re-created under a verified interactive session.
                db.execSQL(
                    "ALTER TABLE offline_events ADD COLUMN authBindingId TEXT NOT NULL DEFAULT ''",
                )
                db.execSQL(
                    "ALTER TABLE auth_session ADD COLUMN authBindingId TEXT NOT NULL DEFAULT ''",
                )
            }
        }

        private val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "ALTER TABLE offline_events ADD COLUMN quarantineReason TEXT DEFAULT NULL",
                )
                db.execSQL(
                    "ALTER TABLE offline_events ADD COLUMN lastServerCode TEXT DEFAULT NULL",
                )
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_offline_events_state_nextAttemptAt " +
                        "ON offline_events(state,nextAttemptAt)",
                )
            }
        }

        private val MIGRATION_4_5 = object : Migration(4, 5) {
            override fun migrate(db: SupportSQLiteDatabase) {
                // Recovery metadata is deliberately separate from immutable event
                // identity/payload fields. A review case can be attached without
                // rewriting or promoting quarantined count evidence.
                db.execSQL(
                    "ALTER TABLE offline_events ADD COLUMN recoveryCaseId TEXT DEFAULT NULL",
                )
                db.execSQL(
                    "ALTER TABLE offline_events ADD COLUMN recoveryState TEXT DEFAULT NULL",
                )
            }
        }

        fun get(context: Context): InventoryDatabase = instance ?: synchronized(this) {
            instance ?: build(context.applicationContext).also { instance = it }
        }

        private fun build(context: Context): InventoryDatabase {
            System.loadLibrary("sqlcipher")
            val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            if (!keyStore.containsAlias(KEY_ALIAS)) {
                KeyGenerator.getInstance(
                    KeyProperties.KEY_ALGORITHM_AES,
                    "AndroidKeyStore",
                ).apply {
                    init(
                        KeyGenParameterSpec.Builder(
                            KEY_ALIAS,
                            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                        )
                            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                            .build(),
                    )
                    generateKey()
                }
            }
            val key = keyStore.getKey(KEY_ALIAS, null) as SecretKey
            val passphrase = loadOrCreatePassphrase(context, key)
            return Room.databaseBuilder(
                context,
                InventoryDatabase::class.java,
                "eay-inventory-offline.db",
            )
                .openHelperFactory(SupportOpenHelperFactory(passphrase))
                .addMigrations(MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5)
                .build()
        }

        private fun loadOrCreatePassphrase(
            context: Context,
            key: SecretKey,
        ): ByteArray {
            val prefs = context.getSharedPreferences(
                "eay_room_key_envelope",
                Context.MODE_PRIVATE,
            )
            val wrapped = prefs.getString("wrapped", null)
            val iv = prefs.getString("iv", null)
            if (wrapped != null && iv != null) {
                return Cipher.getInstance("AES/GCM/NoPadding").run {
                    init(
                        Cipher.DECRYPT_MODE,
                        key,
                        GCMParameterSpec(128, Base64.getDecoder().decode(iv)),
                    )
                    doFinal(Base64.getDecoder().decode(wrapped))
                }
            }
            val randomPassphrase = ByteArray(32).also { SecureRandom().nextBytes(it) }
            val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
                init(Cipher.ENCRYPT_MODE, key)
            }
            val ciphertext = cipher.doFinal(randomPassphrase)
            check(
                prefs.edit()
                    .putString(
                        "wrapped",
                        Base64.getEncoder().encodeToString(ciphertext),
                    )
                    .putString(
                        "iv",
                        Base64.getEncoder().encodeToString(cipher.iv),
                    )
                    .commit(),
            ) { "Unable to seal SQLCipher key" }
            return randomPassphrase
        }
    }
}

object QueueIntegrity {
    fun failureReason(
        event: OfflineEvent,
        currentAuthBindingId: String,
    ): com.eay.mobile.core.SyncQuarantineReason? {
        if (
            currentAuthBindingId.isBlank() ||
            event.authBindingId.isBlank() ||
            event.authBindingId != currentAuthBindingId
        ) {
            return com.eay.mobile.core.SyncQuarantineReason.AUTH_BINDING_CHANGED
        }
        val actual = MessageDigest.getInstance("SHA-256")
            .digest(event.canonicalPayload.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        if (actual != event.payloadHash) {
            return com.eay.mobile.core.SyncQuarantineReason.CORRUPT_EVENT
        }
        return null
    }

    fun valid(event: OfflineEvent, currentAuthBindingId: String): Boolean =
        failureReason(event, currentAuthBindingId) == null
}

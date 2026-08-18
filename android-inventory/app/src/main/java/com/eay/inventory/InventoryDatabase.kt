package com.eay.inventory

import android.content.Context
import android.util.Base64
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
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

@Entity(
    tableName = "offline_events",
    indices = [
        Index(value = ["deviceSequence"], unique = true),
        Index(value = ["state", "nextAttemptAt"]),
    ],
)
data class OfflineEvent(
    @PrimaryKey val eventId: String,
    val deviceSequence: Long,
    val canonicalPayload: String,
    val payloadHash: String,
    val state: String = "PENDING",
    val attempts: Int = 0,
    val nextAttemptAt: Long = 0,
    val authBindingId: String = "",
    val quarantineReason: String? = null,
    val lastServerCode: String? = null,
)

@Entity(tableName = "sequence_state")
data class SequenceState(
    @PrimaryKey val id: Int = 1,
    val nextValue: Long = 1,
)

@Entity(tableName = "auth_session")
data class AuthSession(
    @PrimaryKey val id: Int = 1,
    val refreshToken: String,
    val tokenEndpoint: String,
    val clientId: String,
    val authBindingId: String = "",
)

@Dao
interface OfflineEventDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(event: OfflineEvent)

    @Query("SELECT * FROM offline_events WHERE eventId=:eventId LIMIT 1")
    suspend fun byEventId(eventId: String): OfflineEvent?

    @Query("SELECT * FROM offline_events WHERE deviceSequence=:deviceSequence LIMIT 1")
    suspend fun byDeviceSequence(deviceSequence: Long): OfflineEvent?

    @Query(
        "SELECT * FROM offline_events " +
            "WHERE state IN ('PENDING','RETRY_WAIT') AND nextAttemptAt<=:now " +
            "ORDER BY deviceSequence LIMIT :limit",
    )
    suspend fun due(now: Long, limit: Int = 100): List<OfflineEvent>

    @Query(
        "UPDATE offline_events SET state='ACKED', quarantineReason=NULL, " +
            "lastServerCode=:serverCode, nextAttemptAt=0 WHERE eventId=:eventId",
    )
    suspend fun ack(eventId: String, serverCode: String)

    @Query(
        "UPDATE offline_events SET state='RETRY_WAIT', attempts=attempts+1, " +
            "nextAttemptAt=:whenAt, quarantineReason=NULL, lastServerCode=:serverCode " +
            "WHERE eventId=:eventId",
    )
    suspend fun retry(eventId: String, whenAt: Long, serverCode: String)

    @Query(
        "UPDATE offline_events SET state='QUARANTINED', quarantineReason=:reason, " +
            "lastServerCode=:serverCode, nextAttemptAt=0 WHERE eventId=:eventId",
    )
    suspend fun quarantine(eventId: String, reason: String, serverCode: String)

    @Query("SELECT COUNT(*) FROM offline_events WHERE state IN ('PENDING','RETRY_WAIT')")
    suspend fun pendingCount(): Int

    @Query("SELECT COUNT(*) FROM offline_events WHERE state='QUARANTINED'")
    suspend fun quarantinedCount(): Int
}

@Dao
interface SequenceDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun initialize(state: SequenceState = SequenceState())

    @Query("SELECT nextValue FROM sequence_state WHERE id=1")
    suspend fun peek(): Long

    @Query("UPDATE sequence_state SET nextValue=nextValue+1 WHERE id=1")
    suspend fun increment()
}

@Dao
interface AuthSessionDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(session: AuthSession)

    @Query("SELECT * FROM auth_session WHERE id=1 LIMIT 1")
    suspend fun current(): AuthSession?

    @Query("DELETE FROM auth_session")
    suspend fun clear()
}

@Database(
    entities = [OfflineEvent::class, SequenceState::class, AuthSession::class],
    version = 4,
    exportSchema = true,
)
abstract class InventoryDatabase : RoomDatabase() {
    abstract fun events(): OfflineEventDao
    abstract fun sequences(): SequenceDao
    abstract fun sessions(): AuthSessionDao

    companion object {
        @Volatile private var INSTANCE: InventoryDatabase? = null

        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE auth_session ADD COLUMN authBindingId TEXT NOT NULL DEFAULT ''")
            }
        }

        val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE offline_events ADD COLUMN authBindingId TEXT NOT NULL DEFAULT ''")
                // Pre-binding queued events are intentionally made non-replayable.
                db.execSQL("UPDATE offline_events SET state='ACKED' WHERE authBindingId='' AND state='PENDING'")
            }
        }

        val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE offline_events ADD COLUMN quarantineReason TEXT DEFAULT NULL")
                db.execSQL("ALTER TABLE offline_events ADD COLUMN lastServerCode TEXT DEFAULT NULL")
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_offline_events_state_nextAttemptAt " +
                        "ON offline_events(state,nextAttemptAt)",
                )
            }
        }

        fun get(context: Context): InventoryDatabase = INSTANCE ?: synchronized(this) {
            INSTANCE ?: build(context.applicationContext).also { INSTANCE = it }
        }

        private fun build(context: Context): InventoryDatabase {
            val passphrase = DatabaseKeyStore.passphrase(context)
            return Room.databaseBuilder(context, InventoryDatabase::class.java, "eay_inventory.db")
                .openHelperFactory(SupportOpenHelperFactory(passphrase))
                .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
                .build()
        }
    }
}

object DatabaseKeyStore {
    private const val PREF = "eay.inventory.crypto"
    private const val WRAPPED = "wrapped_db_key"
    private const val IV = "wrapped_db_iv"
    private const val ALIAS = "eay.inventory.db.wrap.v1"

    fun passphrase(context: Context): ByteArray {
        val prefs = context.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val stored = prefs.getString(WRAPPED, null)
        val iv = prefs.getString(IV, null)
        val key = wrapKey()
        if (stored != null && iv != null) {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)),
            )
            return cipher.doFinal(Base64.decode(stored, Base64.NO_WRAP))
        }
        val raw = ByteArray(32).also { java.security.SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key)
        prefs.edit()
            .putString(WRAPPED, Base64.encodeToString(cipher.doFinal(raw), Base64.NO_WRAP))
            .putString(IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .apply()
        return raw
    }

    private fun wrapKey(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(
            android.security.keystore.KeyProperties.KEY_ALGORITHM_AES,
            "AndroidKeyStore",
        )
        generator.init(
            android.security.keystore.KeyGenParameterSpec.Builder(
                ALIAS,
                android.security.keystore.KeyProperties.PURPOSE_ENCRYPT or
                    android.security.keystore.KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(android.security.keystore.KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_NONE)
                .build(),
        )
        return generator.generateKey()
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

object OfflineEventIdentity {
    fun sameImmutableIdentity(left: OfflineEvent, right: OfflineEvent): Boolean =
        left.eventId == right.eventId &&
            left.deviceSequence == right.deviceSequence &&
            left.canonicalPayload == right.canonicalPayload &&
            left.payloadHash == right.payloadHash &&
            left.authBindingId == right.authBindingId
}

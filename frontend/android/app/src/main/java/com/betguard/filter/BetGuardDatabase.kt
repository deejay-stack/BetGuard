package com.betguard.filter

import android.content.Context
import androidx.room.*

@Entity(tableName = "domain_rules")
data class RuleEntity(
    @PrimaryKey val domain: String,
    val action: String,
    val includeSubdomains: Boolean,
    val updatedAt: Long,
)

@Entity(tableName = "history")
data class HistoryEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val kind: String,
    val domain: String,
    val detail: String,
    val createdAt: Long,
)

@Dao
interface BetGuardDao {
    @Query("SELECT * FROM domain_rules ORDER BY updatedAt DESC") fun rules(): List<RuleEntity>
    @Upsert fun save(rule: RuleEntity)
    @Query("DELETE FROM domain_rules WHERE domain = :domain") fun remove(domain: String)
    @Insert fun insert(event: HistoryEntity)
    @Query("SELECT * FROM history ORDER BY id DESC LIMIT 200") fun history(): List<HistoryEntity>
    @Query("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 200)") fun prune()
    @Query("DELETE FROM history") fun clearHistory()
}

@Database(entities = [RuleEntity::class, HistoryEntity::class], version = 1, exportSchema = true)
abstract class BetGuardDatabase : RoomDatabase() {
    abstract fun dao(): BetGuardDao
    companion object {
        fun create(context: Context) = Room.databaseBuilder(
            context.applicationContext, BetGuardDatabase::class.java, "betguard.db"
        ).build()
    }
}

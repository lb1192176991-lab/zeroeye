# Data Directory

This directory contains data files used by the Tent of Trials platform.

## Contents

| File/Directory | Description | Format | Update Frequency |
|---------------|-------------|--------|-----------------|
| `schema.sql` | Database schema definition | SQL | Per migration |
| `seed.sql` | Seed data for development | SQL | Per release |
| `migration.sql` | Pending database migrations | SQL | Per deployment |
| `reference/` | Reference data (instruments, exchanges) | JSON | Weekly |
| `test/` | Test data for development | JSON | Manual |
| `tools/` | Data generation tools | Python | Manual |
| `backup/` | Database backup snapshots | SQL | Daily |

## Schema Files

The `schema.sql` file contains the complete database schema. It is auto-generated
from the migration files and may not reflect the current state of the database
if migrations have been applied manually. For the authoritative schema, query
the `information_schema` tables directly.

## Seed Data

The `seed.sql` file contains seed data for development environments only.
It creates sample users, instruments, and configuration that make the
application usable immediately after deployment.

WARNING: The seed data includes test API keys and passwords that are publicly
visible in this repository. Do NOT use these credentials in production.
The seed data is intended for local development only.

## Migration Files

Migration files follow the naming convention: `{YYYYMMDDHHMMSS}_{description}.sql`
Migration files are applied in order by the migration tool. The migration state
is tracked in the `_migrations` table in the database.

Pending migrations that have not yet been applied to production:
- 20240701000000_add_analytics_rollups.sql (in review)
- 20240715000000_add_user_activity_indexes.sql (in review)

## Data Generation Tools

The `tools/` directory contains data generation utilities for creating deterministic test data:

- `data_generator.py`: A comprehensive data generator for creating reproducible test data including users, orders, trades, and market ticks. Uses seeding to ensure identical datasets can be generated consistently.

### Using the Data Generator

To generate deterministic test data:

```bash
# Generate data with a specific seed for reproducibility
python tools/data_generator.py --seed 12345 --users 100 --orders 500 --trades 1000

# Generate data without specifying seed (uses default)
python tools/data_generator.py --users 50 --orders 200

# Generate only specific data types
python tools/data_generator.py --users 20 --no-orders --no-trades
```

The data generator creates reproducible datasets by using a deterministic random seed. Using the same seed will always produce identical data, which is essential for testing and debugging scenarios that need consistent results.

## Backup Files

Database backup snapshots are stored in the `backup/` directory. These are
created by the automated backup system and are retained for 30 days. The
backup files are compressed with gzip and encrypted with GPG.

To restore a backup:
```bash
gpg -d backup/tent_production_20240101.sql.gz | gunzip | psql -h localhost tent_production
```

The GPG key ID is stored in the team vault under `secret/database/backup-key`.

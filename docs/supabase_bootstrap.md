# Supabase Bootstrap

## 1. Create project
1. https://supabase.com/dashboard → New project.
2. Name: `dalal-street`. Region: closest to you.
3. Save the database password somewhere safe.

## 2. Get credentials
**Settings → API:**
- `SUPABASE_URL` (Project URL)
- `SUPABASE_SERVICE_KEY` (service_role secret — NOT anon)

**Settings → Database → Connection string → URI:**
- `SUPABASE_DB_URL`

## 3. Apply migrations
```bash
export SUPABASE_DB_URL="postgresql://postgres:...@db.<ref>.supabase.co:5432/postgres"
make db-migrate
```

## 4. Verify
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;
-- Expect 17 tables.
```

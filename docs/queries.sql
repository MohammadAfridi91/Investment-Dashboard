-- Last 5 EOD runs
SELECT workflow, status, started_at, duration_seconds, rows_processed, error_message
FROM pipeline_health WHERE workflow = 'eod'
ORDER BY started_at DESC LIMIT 5;

-- Recent bhavcopy ingestion coverage
SELECT trade_date, COUNT(*) AS symbols, MAX(ingested_at) AS last_ingest
FROM daily_prices GROUP BY trade_date ORDER BY trade_date DESC LIMIT 10;

-- Universe composition
SELECT is_nifty500, is_midsmall400, is_bfsi, COUNT(*)
FROM universe GROUP BY 1,2,3 ORDER BY 1 DESC, 2 DESC;

-- Stale heartbeats (last 7 days)
SELECT * FROM pipeline_health
WHERE status IN ('FAILED','DELAYED') AND started_at > NOW() - INTERVAL '7 days'
ORDER BY started_at DESC;

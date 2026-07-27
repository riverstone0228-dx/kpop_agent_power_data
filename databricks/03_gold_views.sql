-- Gold VIEW: 7日差分などはここで計算（rawに持たない）

CREATE OR REPLACE VIEW workspace.kpop_gold.v_artist_daily_with_lag AS
SELECT
  a.*,
  LAG(youtube_subscribers) OVER (
    PARTITION BY agency, artist_name ORDER BY date
  ) AS youtube_subscribers_prev,
  LAG(youtube_total_views) OVER (
    PARTITION BY agency, artist_name ORDER BY date
  ) AS youtube_total_views_prev
FROM workspace.kpop_bronze.fact_artist_daily a;

CREATE OR REPLACE VIEW workspace.kpop_gold.v_artist_metrics_7d AS
SELECT
  cur.date,
  cur.agency,
  cur.sub_agency,
  cur.artist_name,
  cur.youtube_subscribers,
  cur.youtube_total_views,
  cur.wikipedia_pv_ja,
  cur.wikipedia_pv_en,
  cur.youtube_subscribers - prev.youtube_subscribers AS subscribers_delta_7d,
  cur.youtube_total_views - prev.youtube_total_views AS views_delta_7d
FROM workspace.kpop_bronze.fact_artist_daily cur
LEFT JOIN workspace.kpop_bronze.fact_artist_daily prev
  ON cur.agency = prev.agency
 AND cur.artist_name = prev.artist_name
 AND prev.date = date_add(cur.date, -7);

CREATE OR REPLACE VIEW workspace.kpop_gold.v_agency_power_daily AS
SELECT
  date,
  agency,
  COUNT(*) AS artist_count,
  SUM(youtube_subscribers) AS youtube_subscribers,
  SUM(youtube_total_views) AS youtube_total_views,
  SUM(COALESCE(wikipedia_pv_ja, 0) + COALESCE(wikipedia_pv_en, 0)) AS wikipedia_pv
FROM workspace.kpop_bronze.fact_artist_daily
GROUP BY date, agency;

CREATE OR REPLACE VIEW workspace.kpop_gold.v_song_rank_latest AS
SELECT *
FROM workspace.kpop_bronze.fact_song_rank_daily
WHERE date = (SELECT MAX(date) FROM workspace.kpop_bronze.fact_song_rank_daily);

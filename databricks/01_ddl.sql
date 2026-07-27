-- RIVERSTONE K-POP · Databricks Free Edition DDL
-- 既定カタログ `workspace` を使う（Free Edition で確実）。
-- SQL Editor または Notebook (%sql) で上から実行。

CREATE SCHEMA IF NOT EXISTS workspace.kpop_bronze
COMMENT '生に近い取り込み (日次CSVを統合したDelta)';

CREATE SCHEMA IF NOT EXISTS workspace.kpop_gold
COMMENT '分析・レポート用VIEW / ランキング';

-- ---------------------------------------------------------------------------
-- Dimensions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS workspace.kpop_bronze.dim_artist (
  agency STRING,
  sub_agency STRING,
  artist_name_en STRING,
  artist_name_ja STRING,
  youtube_channel_id STRING,
  apple_artist_id STRING,
  wikipedia_title_ja STRING,
  wikipedia_title_en STRING,
  status STRING,
  notes STRING,
  image_url STRING,
  source_file STRING,
  loaded_at TIMESTAMP
)
USING DELTA
COMMENT 'アーティストマスタ (artist_master + other_agency_master)';

CREATE TABLE IF NOT EXISTS workspace.kpop_bronze.dim_track (
  track_id STRING,
  agency STRING,
  sub_agency STRING,
  artist_name_en STRING,
  track_name STRING,
  release_date STRING,
  track_type STRING,
  youtube_video_id STRING,
  artwork_url STRING,
  selection_reason STRING,
  status STRING,
  platforms STRING,
  first_seen STRING,
  last_seen STRING,
  loaded_at TIMESTAMP
)
USING DELTA;

-- ---------------------------------------------------------------------------
-- Facts (日別CSVを1テーブルに統合)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS workspace.kpop_bronze.fact_artist_daily (
  date DATE,
  agency STRING,
  sub_agency STRING,
  artist_name STRING,
  youtube_subscribers BIGINT,
  youtube_total_views BIGINT,
  youtube_video_count BIGINT,
  wikipedia_pv_ja BIGINT,
  wikipedia_pv_en BIGINT,
  youtube_channel_thumbnail STRING,
  loaded_at TIMESTAMP
)
USING DELTA
PARTITIONED BY (date)
COMMENT 'data/raw/YYYY-MM-DD.csv の統合';

CREATE TABLE IF NOT EXISTS workspace.kpop_bronze.fact_apple_chart_daily (
  date DATE,
  feed_updated STRING,
  country STRING,
  rank INT,
  track_name STRING,
  artist_name_local STRING,
  apple_artist_id STRING,
  apple_track_id STRING,
  release_date STRING,
  artwork_url STRING,
  is_kpop_genre STRING,
  agency STRING,
  sub_agency STRING,
  artist_name_master STRING,
  loaded_at TIMESTAMP
)
USING DELTA
PARTITIONED BY (date);

CREATE TABLE IF NOT EXISTS workspace.kpop_bronze.fact_line_chart_daily (
  date DATE,
  chart_date DATE,
  rank INT,
  rank_variation INT,
  is_new STRING,
  track_name STRING,
  artist_name_local STRING,
  line_artist_id STRING,
  line_track_id STRING,
  score DOUBLE,
  listened_count BIGINT,
  like_count BIGINT,
  artist_image_url STRING,
  album_image_url STRING,
  agency STRING,
  sub_agency STRING,
  artist_name_master STRING,
  match_status STRING,
  source_entry_url STRING,
  loaded_at TIMESTAMP
)
USING DELTA
PARTITIONED BY (date);

CREATE TABLE IF NOT EXISTS workspace.kpop_bronze.fact_youtube_video_daily (
  date DATE,
  agency STRING,
  sub_agency STRING,
  artist_name STRING,
  youtube_channel_id STRING,
  selection STRING,
  rank INT,
  video_id STRING,
  title STRING,
  url STRING,
  published_at STRING,
  view_count BIGINT,
  like_count BIGINT,
  comment_count BIGINT,
  thumbnail_url STRING,
  loaded_at TIMESTAMP
)
USING DELTA
PARTITIONED BY (date);

CREATE TABLE IF NOT EXISTS workspace.kpop_bronze.fact_song_rank_daily (
  date DATE,
  rank_type STRING,   -- top / hot
  rank INT,
  track_id STRING,
  artist_name_en STRING,
  track_name STRING,
  agency STRING,
  sub_agency STRING,
  score DOUBLE,
  chart_points DOUBLE,
  chart_delta DOUBLE,
  youtube_views BIGINT,
  platforms STRING,
  youtube_video_id STRING,
  agency_logo_url STRING,
  artist_image_url STRING,
  artwork_url STRING,
  youtube_thumbnail_url STRING,
  loaded_at TIMESTAMP
)
USING DELTA
PARTITIONED BY (date);

create table if not exists ai_model_leaderboard (
  model_name    text not null,
  organization  text not null,
  category      text not null,
  rank          int  not null,
  rating        numeric not null,
  vote_count    bigint not null,
  snapshot_date date not null,
  fetched_at    timestamptz not null default now(),
  primary key (category, model_name, snapshot_date)
);

create index if not exists ai_model_leaderboard_snapshot_idx
  on ai_model_leaderboard (snapshot_date desc);

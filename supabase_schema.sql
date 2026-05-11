-- Run this in your Supabase project: Dashboard → SQL Editor → New query

create table if not exists memories (
    id          bigserial primary key,
    type        text not null default 'fact',   -- fact | preference | event | task
    content     text not null,
    tags        text[] default '{}',
    importance  int  default 1,                 -- 1=low 2=medium 3=high
    created_at  timestamptz default now(),
    updated_at  timestamptz default now()
);

create table if not exists conversations (
    id           bigserial primary key,
    user_msg     text,
    jarvis_reply text,
    tools_used   text[] default '{}',
    created_at   timestamptz default now()
);

-- Index for fast memory search
create index if not exists memories_content_idx on memories using gin(to_tsvector('english', content));
create index if not exists memories_importance_idx on memories(importance desc);
create index if not exists memories_type_idx on memories(type);

-- Enable Row Level Security (open for now since it's private)
alter table memories      enable row level security;
alter table conversations enable row level security;

create policy "allow all" on memories      for all using (true) with check (true);
create policy "allow all" on conversations for all using (true) with check (true);

CREATE SCHEMA IF NOT EXISTS avo;
CREATE TABLE IF NOT EXISTS avo.sessions(id text primary key,role text not null,expires_at timestamptz not null);
CREATE TABLE IF NOT EXISTS avo.evidence(id text primary key,event_id text unique not null,actor text not null,photo text,original_photo text,sha256 text,message text not null default '',observation text,created_at timestamptz default now());
CREATE TABLE IF NOT EXISTS avo.drafts(id text primary key,evidence_id text references avo.evidence(id),version integer not null default 1,state text not null default 'draft',fields jsonb not null,questions jsonb not null default '[]',product_id text,variant_id text,inventory_id text,last_error text,applied_version integer,created_at timestamptz default now(),updated_at timestamptz default now());
CREATE TABLE IF NOT EXISTS avo.audit(id text primary key,actor text not null,action text not null,subject text not null,before_data jsonb,after_data jsonb,event_id text unique,created_at timestamptz default now());
CREATE TABLE IF NOT EXISTS avo.content(id text primary key,version integer not null default 1,published jsonb not null,draft jsonb,updated_at timestamptz default now());
CREATE TABLE IF NOT EXISTS avo.slots(id text primary key,label text not null,starts_at timestamptz not null,ends_at timestamptz not null,cutoff timestamptz not null,capacity integer not null check(capacity>0),active boolean not null default true);
CREATE TABLE IF NOT EXISTS avo.boxes(id text primary key,version integer not null default 1,state text not null default 'draft',name text not null,price_minor integer,recipe jsonb not null default '[]',swap jsonb,updated_at timestamptz default now());
CREATE TABLE IF NOT EXISTS avo.attempts(id text primary key,cart_id text not null,revision text not null unique,slot_id text references avo.slots(id),state text not null default 'pending',snapshot jsonb not null,provider_session text,payment_collection_id text,order_id text,expires_at timestamptz not null,created_at timestamptz default now());
CREATE TABLE IF NOT EXISTS avo.events(id text primary key,provider text not null,payload jsonb not null,state text not null default 'received',last_error text,created_at timestamptz default now());
CREATE TABLE IF NOT EXISTS avo.tasks(id text primary key,order_id text not null unique,attempt_id text references avo.attempts(id),state text not null default 'paid',assignee text,actual_contents jsonb,exception text,created_at timestamptz default now(),updated_at timestamptz default now());
CREATE TABLE IF NOT EXISTS avo.settings(key text primary key,value jsonb not null);

ALTER TABLE avo.attempts ADD COLUMN IF NOT EXISTS owner_session text;
ALTER TABLE avo.attempts ADD COLUMN IF NOT EXISTS last_error text;

ALTER TABLE avo.boxes ADD COLUMN IF NOT EXISTS fields jsonb;
ALTER TABLE avo.boxes ADD COLUMN IF NOT EXISTS product_id text;
ALTER TABLE avo.boxes ADD COLUMN IF NOT EXISTS evidence_id text REFERENCES avo.evidence(id);
CREATE TABLE IF NOT EXISTS avo.movements(id text PRIMARY KEY,event_id text UNIQUE NOT NULL,product_id text NOT NULL,inventory_id text NOT NULL,action text NOT NULL,quantity integer NOT NULL,reason text NOT NULL,before_quantity integer NOT NULL,target_quantity integer NOT NULL,state text NOT NULL DEFAULT 'pending',actor text NOT NULL,last_error text,created_at timestamptz DEFAULT now());
ALTER TABLE avo.slots ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
ALTER TABLE avo.evidence ADD COLUMN IF NOT EXISTS photos jsonb NOT NULL DEFAULT '[]';
CREATE TABLE IF NOT EXISTS avo.marketing_drafts(id text PRIMARY KEY,event_id text UNIQUE NOT NULL,product_id text NOT NULL,fields jsonb NOT NULL,actor text NOT NULL,created_at timestamptz DEFAULT now());
ALTER TABLE avo.drafts ADD COLUMN IF NOT EXISTS parent_draft_id text REFERENCES avo.drafts(id);
CREATE TABLE IF NOT EXISTS avo.draft_events(event_id text PRIMARY KEY,source_draft_id text NOT NULL REFERENCES avo.drafts(id),created_draft_id text NOT NULL REFERENCES avo.drafts(id),actor text NOT NULL,created_at timestamptz DEFAULT now());
ALTER TABLE avo.drafts ADD COLUMN IF NOT EXISTS owner_message text NOT NULL DEFAULT '';

ALTER TABLE avo.movements ADD COLUMN IF NOT EXISTS corrects_movement_id text REFERENCES avo.movements(id);

ALTER TABLE avo.boxes ADD COLUMN IF NOT EXISTS source_box_id text REFERENCES avo.boxes(id);
ALTER TABLE avo.boxes ADD COLUMN IF NOT EXISTS source_box_version integer;
ALTER TABLE avo.boxes ADD COLUMN IF NOT EXISTS revision_event_id text UNIQUE;

CREATE TABLE IF NOT EXISTS avo.pickup_proposals(id text PRIMARY KEY,event_id text UNIQUE NOT NULL,version integer NOT NULL DEFAULT 1,state text NOT NULL DEFAULT 'draft',fields jsonb NOT NULL,actor text NOT NULL,created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS avo.scheduled_specials(id text PRIMARY KEY,event_id text UNIQUE NOT NULL,version integer NOT NULL DEFAULT 1,state text NOT NULL DEFAULT 'draft',fields jsonb NOT NULL,price_list_id text,last_error text,actor text NOT NULL,created_at timestamptz DEFAULT now(),updated_at timestamptz DEFAULT now());

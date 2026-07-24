begin;

-- Phase 5: owner notifications, project inquiries, participant inbox, and
-- strict administrator audit delivery. Supabase Auth remains authoritative
-- for identity; guest email delivery is deliberately not inferred here.

create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  public_reference text not null unique
    check (public_reference ~ '^INQ-[A-F0-9]{12}$'),
  recipient_user_id uuid not null references public.users(id) on delete restrict,
  initiator_user_id uuid references public.users(id) on delete restrict,
  sender_name text not null check (length(sender_name) between 1 and 120),
  sender_email text not null check (
    length(sender_email) between 3 and 180
    and sender_email = lower(sender_email)
    and sender_email ~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$'
    and sender_email !~ '[[:cntrl:]]'
  ),
  inquiry_type text not null check (
    inquiry_type in ('exhibition', 'editorial', 'licensing', 'print', 'commission', 'other')
  ),
  organization text check (
    organization is null or length(organization) between 1 and 180
  ),
  project_use text not null check (length(project_use) between 5 and 280),
  timeline text check (timeline is null or length(timeline) between 1 and 120),
  budget_range text check (budget_range is null or length(budget_range) between 1 and 120),
  status text not null default 'open'
    check (status in ('open', 'replied', 'closed')),
  version integer not null default 1 check (version > 0),
  rate_limit_key char(64) not null check (rate_limit_key ~ '^[0-9a-f]{64}$'),
  request_fingerprint char(64) not null check (request_fingerprint ~ '^[0-9a-f]{64}$'),
  idempotency_key uuid not null unique,
  last_message_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (initiator_user_id is null or initiator_user_id <> recipient_user_id)
);

create table if not exists public.conversation_participants (
  conversation_id uuid not null references public.conversations(id) on delete restrict,
  user_id uuid not null references public.users(id) on delete restrict,
  participant_role text not null check (participant_role in ('sender', 'recipient')),
  last_read_message_id uuid,
  last_read_at timestamptz,
  joined_at timestamptz not null default now(),
  primary key (conversation_id, user_id),
  unique (conversation_id, participant_role),
  check ((last_read_message_id is null) = (last_read_at is null))
);

create table if not exists public.conversation_works (
  conversation_id uuid not null references public.conversations(id) on delete restrict,
  image_id uuid not null references public.images(id) on delete restrict,
  owner_user_id uuid not null references public.users(id) on delete restrict,
  position integer not null check (position between 1 and 10),
  created_at timestamptz not null default now(),
  primary key (conversation_id, image_id),
  unique (conversation_id, position)
);

create table if not exists public.conversation_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete restrict,
  sender_user_id uuid references public.users(id) on delete restrict,
  sender_kind text not null check (sender_kind in ('guest', 'member')),
  sender_display_name text not null check (length(sender_display_name) between 1 and 120),
  body text not null check (length(body) between 1 and 5000),
  delivery_status text not null check (
    delivery_status in ('recorded', 'provider_unavailable')
  ),
  is_initial boolean not null default false,
  expected_conversation_version integer check (
    expected_conversation_version is null or expected_conversation_version > 0
  ),
  result_conversation_version integer not null check (result_conversation_version > 0),
  request_fingerprint char(64) not null check (request_fingerprint ~ '^[0-9a-f]{64}$'),
  idempotency_key uuid not null unique,
  created_at timestamptz not null default now(),
  check (
    (is_initial and expected_conversation_version is null and result_conversation_version = 1)
    or (
      not is_initial
      and expected_conversation_version is not null
      and result_conversation_version = expected_conversation_version + 1
    )
  ),
  check (
    (sender_kind = 'guest' and sender_user_id is null and is_initial)
    or (sender_kind = 'member' and sender_user_id is not null)
  )
);

create table if not exists public.conversation_status_actions (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null
    references public.conversations(id) on delete restrict,
  actor_user_id uuid not null references public.users(id) on delete restrict,
  target_status text not null check (target_status in ('open', 'closed')),
  expected_conversation_version integer not null
    check (expected_conversation_version > 0),
  result_conversation_version integer not null
    check (result_conversation_version = expected_conversation_version + 1),
  delivery_status text not null check (
    delivery_status in ('recorded', 'provider_unavailable')
  ),
  request_fingerprint char(64) not null
    check (request_fingerprint ~ '^[0-9a-f]{64}$'),
  idempotency_key uuid not null unique,
  result_snapshot jsonb not null check (jsonb_typeof(result_snapshot) = 'object'),
  created_at timestamptz not null default now()
);

create table if not exists public.audit_export_actions (
  id uuid primary key default gen_random_uuid(),
  actor_user_id uuid not null references public.users(id) on delete restrict,
  actor_role public.role_code not null,
  reason_code text not null check (
    reason_code in (
      'operational_review', 'security_investigation', 'compliance_request'
    )
  ),
  filters jsonb not null check (jsonb_typeof(filters) = 'object'),
  export_limit integer not null check (export_limit between 1 and 1000),
  request_fingerprint char(64) not null
    check (request_fingerprint ~ '^[0-9a-f]{64}$'),
  idempotency_key uuid not null unique,
  result_snapshot jsonb not null check (jsonb_typeof(result_snapshot) = 'object'),
  audit_event_id uuid not null unique
    references public.audit_logs(id) on delete restrict,
  created_at timestamptz not null default now()
);

create unique index if not exists conversation_messages_one_initial_idx
  on public.conversation_messages (conversation_id) where is_initial;
create index if not exists conversations_recipient_activity_idx
  on public.conversations (recipient_user_id, last_message_at desc, id);
create index if not exists conversations_initiator_activity_idx
  on public.conversations (initiator_user_id, last_message_at desc, id)
  where initiator_user_id is not null;
create index if not exists conversations_rate_limit_idx
  on public.conversations (rate_limit_key, created_at desc);
create index if not exists conversation_messages_conversation_created_idx
  on public.conversation_messages (conversation_id, created_at desc, id);
create unique index if not exists conversation_messages_conversation_id_id_uq
  on public.conversation_messages (conversation_id, id);
create index if not exists conversation_participants_user_idx
  on public.conversation_participants (user_id, conversation_id);
create index if not exists conversation_status_actions_conversation_created_idx
  on public.conversation_status_actions (conversation_id, created_at desc, id);
create index if not exists audit_export_actions_actor_created_idx
  on public.audit_export_actions (actor_user_id, created_at desc, id);
create index if not exists notifications_recipient_created_idx
  on public.notifications (recipient_user_id, created_at desc, id);
create index if not exists notifications_recipient_unread_idx
  on public.notifications (recipient_user_id, created_at desc, id)
  where read_at is null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.conversation_participants'::regclass
      and conname = 'conversation_participants_read_message_fk'
  ) then
    alter table public.conversation_participants
      add constraint conversation_participants_read_message_fk
      foreign key (conversation_id, last_read_message_id)
      references public.conversation_messages(conversation_id, id)
      on delete restrict;
  end if;
end
$$;

create or replace function public.protect_conversation_identity()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'conversation identity and version history are protected'
      using errcode = '55000';
  end if;
  if new.public_reference is distinct from old.public_reference
     or new.recipient_user_id is distinct from old.recipient_user_id
     or new.initiator_user_id is distinct from old.initiator_user_id
     or new.sender_name is distinct from old.sender_name
     or new.sender_email is distinct from old.sender_email
     or new.inquiry_type is distinct from old.inquiry_type
     or new.organization is distinct from old.organization
     or new.project_use is distinct from old.project_use
     or new.timeline is distinct from old.timeline
     or new.budget_range is distinct from old.budget_range
     or new.rate_limit_key is distinct from old.rate_limit_key
     or new.request_fingerprint is distinct from old.request_fingerprint
     or new.idempotency_key is distinct from old.idempotency_key
     or new.created_at is distinct from old.created_at
     or new.version <> old.version + 1
     or new.last_message_at < old.last_message_at
     or new.updated_at < old.updated_at then
    raise exception 'conversation identity and version history are protected'
      using errcode = '55000';
  end if;
  return new;
end;
$$;

create or replace function public.protect_conversation_participant()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'conversation participant identity is protected'
      using errcode = '55000';
  end if;
  if new.conversation_id is distinct from old.conversation_id
     or new.user_id is distinct from old.user_id
     or new.participant_role is distinct from old.participant_role
     or new.joined_at is distinct from old.joined_at
     or ((new.last_read_message_id is null) <> (new.last_read_at is null))
     or (
       old.last_read_at is not null and (
         new.last_read_at is null
         or (new.last_read_at, new.last_read_message_id)
           < (old.last_read_at, old.last_read_message_id)
       )
     ) then
    raise exception 'conversation participant identity is protected'
      using errcode = '55000';
  end if;
  return new;
end;
$$;

drop trigger if exists conversations_identity_guard on public.conversations;
create trigger conversations_identity_guard
before update or delete on public.conversations
for each row execute function public.protect_conversation_identity();

drop trigger if exists conversation_participants_identity_guard
  on public.conversation_participants;
create trigger conversation_participants_identity_guard
before update or delete on public.conversation_participants
for each row execute function public.protect_conversation_participant();

drop trigger if exists conversation_works_append_only on public.conversation_works;
create trigger conversation_works_append_only
before update or delete on public.conversation_works
for each row execute function public.reject_mutation();

drop trigger if exists conversation_messages_append_only
  on public.conversation_messages;
create trigger conversation_messages_append_only
before update or delete on public.conversation_messages
for each row execute function public.reject_mutation();

drop trigger if exists conversation_status_actions_append_only
  on public.conversation_status_actions;
create trigger conversation_status_actions_append_only
before update or delete on public.conversation_status_actions
for each row execute function public.reject_mutation();

drop trigger if exists audit_export_actions_append_only
  on public.audit_export_actions;
create trigger audit_export_actions_append_only
before update or delete on public.audit_export_actions
for each row execute function public.reject_mutation();

alter table public.conversations enable row level security;
alter table public.conversation_participants enable row level security;
alter table public.conversation_works enable row level security;
alter table public.conversation_messages enable row level security;
alter table public.conversation_status_actions enable row level security;
alter table public.audit_export_actions enable row level security;

revoke all on public.conversations
  from public, anon, authenticated, service_role;
revoke all on public.conversation_participants
  from public, anon, authenticated, service_role;
revoke all on public.conversation_works
  from public, anon, authenticated, service_role;
revoke all on public.conversation_messages
  from public, anon, authenticated, service_role;
revoke all on public.conversation_status_actions
  from public, anon, authenticated, service_role;
revoke all on public.audit_export_actions
  from public, anon, authenticated, service_role;

-- Notifications and audit are now strict RPC-only read models. In particular,
-- owners can no longer alter notification type/payload through a generic row
-- update, and administrators cannot fetch raw audit before/after JSON.
drop policy if exists notifications_owner_select on public.notifications;
drop policy if exists notifications_owner_update on public.notifications;
drop policy if exists audit_owner_activity_select on public.audit_logs;
drop policy if exists admin_audit_select on public.audit_logs;
revoke all on public.notifications
  from public, anon, authenticated, service_role;
revoke all on public.audit_logs
  from public, anon, authenticated, service_role;

create or replace function public.communications_error(code text, message text)
returns jsonb
language sql
immutable
set search_path = ''
as $$
  select jsonb_build_object(
    'error', jsonb_build_object('code', $1, 'message', $2)
  )
$$;

create or replace function public.communications_require_actor(
  require_active boolean default false
)
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_status public.account_status;
begin
  if public.is_recovery_auth_session() then
    raise exception 'recovery session cannot access communications'
      using errcode = '42501';
  end if;
  select public.current_app_user_id() into actor_id;
  select target.account_status into actor_status
  from public.users target where target.id = actor_id;
  if actor_id is null
     or actor_status is null
     or (
       require_active and actor_status <> 'active'::public.account_status
     )
     or (
       not require_active and actor_status not in (
         'active'::public.account_status, 'suspended'::public.account_status
       )
     ) then
    raise exception 'eligible authenticated account required'
      using errcode = '42501';
  end if;
  if exists (
    select 1 from public.user_roles role_row
    where role_row.user_id = actor_id
      and role_row.role in (
        'admin'::public.role_code, 'super_admin'::public.role_code
      )
  ) and not public.has_aal2() then
    raise exception 'aal2 required for administrator communications access'
      using errcode = '42501';
  end if;
  return actor_id;
end;
$$;

create or replace function public.notification_safe_json(notification_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', notification.id,
    'type', left(notification.type, 120),
    'message', case when notification.payload ? 'message'
      then left(regexp_replace(
        notification.payload ->> 'message', '[[:cntrl:]]', ' ', 'g'
      ), 1000)
      else null
    end,
    'href', case
      when notification.type in (
        'project_inquiry_received', 'conversation_reply_received',
        'conversation_status_changed'
      ) and coalesce(notification.payload ->> 'conversation_id', '')
        ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      then '/inbox/' || (notification.payload ->> 'conversation_id')
      when coalesce(notification.payload ->> 'image_id', '')
        ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      then '/workspace/images?image=' || (notification.payload ->> 'image_id')
      when notification.type like 'account\_%' escape '\'
        or notification.type like 'role\_%' escape '\'
        or notification.type like 'admin\_session\_%' escape '\'
      then '/settings/account'
      else '/workspace/notifications'
    end,
    'read_at', notification.read_at,
    'created_at', notification.created_at
  )
  from public.notifications notification
  where notification.id = $1
$$;

create or replace function public.get_my_notification_unread_count()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  unread_count integer;
begin
  actor_id := public.communications_require_actor(true);
  select count(*)::integer into unread_count
  from public.notifications notification
  where notification.recipient_user_id = actor_id
    and notification.read_at is null;
  return jsonb_build_object(
    'unread_count', unread_count
  );
end;
$$;

create or replace function public.list_my_notifications(
  page_limit integer default 30,
  cursor_created_at timestamptz default null,
  cursor_id uuid default null
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  item_rows jsonb;
  unread_count integer;
  candidate_count integer;
  next_created_at timestamptz;
  next_id uuid;
begin
  actor_id := public.communications_require_actor(true);
  if page_limit is null or page_limit not between 1 and 100 then
    return public.communications_error(
      'NOTIFICATION_PAGE_INVALID', 'Use a notification page size from 1 to 100.'
    );
  end if;
  if (cursor_created_at is null) <> (cursor_id is null) then
    return public.communications_error(
      'NOTIFICATION_CURSOR_INVALID', 'Use a complete notification cursor.'
    );
  end if;

  with candidates as (
    select notification.id, notification.created_at,
           row_number() over (
             order by notification.created_at desc, notification.id desc
           ) as row_number
    from public.notifications notification
    where notification.recipient_user_id = actor_id
      and (
        cursor_created_at is null
        or (notification.created_at, notification.id) < (cursor_created_at, cursor_id)
      )
    order by notification.created_at desc, notification.id desc
    limit page_limit + 1
  )
  select
    coalesce(jsonb_agg(
      public.notification_safe_json(candidate.id)
      order by candidate.row_number
    ) filter (where candidate.row_number <= page_limit), '[]'::jsonb),
    count(*)::integer,
    max(candidate.created_at) filter (where candidate.row_number = page_limit),
    (max(candidate.id::text) filter (where candidate.row_number = page_limit))::uuid
  into item_rows, candidate_count, next_created_at, next_id
  from candidates candidate;

  select count(*)::integer into unread_count
  from public.notifications notification
  where notification.recipient_user_id = actor_id
    and notification.read_at is null;

  return jsonb_build_object(
    'items', item_rows,
    'unread_count', unread_count,
    'pagination', jsonb_build_object(
      'limit', page_limit,
      'has_more', candidate_count > page_limit,
      'next_cursor', case when candidate_count > page_limit then jsonb_build_object(
        'created_at', next_created_at,
        'id', next_id
      ) else null end
    )
  );
end;
$$;

create or replace function public.mark_my_notification_read(
  target_notification_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  target public.notifications%rowtype;
  unread_count integer;
begin
  actor_id := public.communications_require_actor(true);
  select * into target
  from public.notifications notification
  where notification.id = target_notification_id
    and notification.recipient_user_id = actor_id
  for update;
  if target.id is null then
    return public.communications_error(
      'NOTIFICATION_NOT_FOUND', 'The notification is unavailable.'
    );
  end if;
  if target.read_at is null then
    update public.notifications notification set read_at = now()
    where notification.id = target.id
    returning * into target;
  end if;
  select count(*)::integer into unread_count
  from public.notifications notification
  where notification.recipient_user_id = actor_id
    and notification.read_at is null;
  return jsonb_build_object(
    'notification', public.notification_safe_json(target.id),
    'unread_count', unread_count
  );
end;
$$;

create or replace function public.mark_all_my_notifications_read()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  marked_count integer;
  marked_at timestamptz := now();
begin
  actor_id := public.communications_require_actor(true);
  update public.notifications notification set read_at = marked_at
  where notification.recipient_user_id = actor_id
    and notification.read_at is null;
  get diagnostics marked_count = row_count;
  return jsonb_build_object(
    'marked_count', marked_count,
    'unread_count', 0,
    'marked_at', marked_at
  );
end;
$$;

create or replace function public.conversation_work_items(
  target_conversation_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', work.image_id,
    'title', coalesce(nullif(version.title, ''), 'Untitled Work'),
    'position', work.position
  ) order by work.position, work.image_id), '[]'::jsonb)
  from public.conversation_works work
  join public.images image
    on image.id = work.image_id and image.owner_user_id = work.owner_user_id
  left join public.image_versions version
    on version.id = image.current_version_id and version.image_id = image.id
  where work.conversation_id = $1
$$;

create or replace function public.conversation_message_json(message_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', message.id,
    'sender_kind', message.sender_kind,
    'sender_role', case
      when message.sender_kind = 'guest' then 'guest'
      else coalesce((
        select participant.participant_role
        from public.conversation_participants participant
        where participant.conversation_id = message.conversation_id
          and participant.user_id = message.sender_user_id
      ), 'member')
    end,
    'sender_display_name', message.sender_display_name,
    'body', message.body,
    'delivery_status', message.delivery_status,
    'created_at', message.created_at
  )
  from public.conversation_messages message
  where message.id = $1
$$;

create or replace function public.conversation_summary_json(
  target_conversation_id uuid,
  viewer_user_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', conversation.id,
    'participant_role', viewer.participant_role,
    'public_reference', conversation.public_reference,
    'status', conversation.status,
    'version', conversation.version,
    'inquiry_type', conversation.inquiry_type,
    'organization', conversation.organization,
    'project_use', conversation.project_use,
    'timeline', conversation.timeline,
    'budget_range', conversation.budget_range,
    'sender', jsonb_build_object(
      'kind', case when conversation.initiator_user_id is null then 'guest' else 'member' end,
      'display_name', conversation.sender_name,
      'email', conversation.sender_email
    ),
    'recipient', jsonb_build_object(
      'display_name', coalesce(
        recipient_profile.display_name,
        nullif(split_part(recipient.email, '@', 1), ''),
        'MT Presence'
      )
    ),
    'works', public.conversation_work_items(conversation.id),
    'work_count', (
      select count(*)::integer from public.conversation_works work
      where work.conversation_id = conversation.id
    ),
    'unread_count', (
      select count(*)::integer
      from public.conversation_messages message
      where message.conversation_id = conversation.id
        and message.sender_user_id is distinct from $2
        and (
          viewer.last_read_at is null
          or (message.created_at, message.id)
            > (viewer.last_read_at, viewer.last_read_message_id)
        )
    ),
    'last_message', public.conversation_message_json(last_message.id),
    'last_message_at', conversation.last_message_at,
    'created_at', conversation.created_at,
    'updated_at', conversation.updated_at
  )
  from public.conversations conversation
  join public.conversation_participants viewer
    on viewer.conversation_id = conversation.id and viewer.user_id = $2
  join public.users recipient on recipient.id = conversation.recipient_user_id
  left join public.user_profiles recipient_profile
    on recipient_profile.user_id = recipient.id
  left join lateral (
    select message.id
    from public.conversation_messages message
    where message.conversation_id = conversation.id
    order by message.created_at desc, message.id desc
    limit 1
  ) last_message on true
  where conversation.id = $1
$$;

create or replace function public.project_inquiry_result(
  initial_message_id uuid,
  replayed boolean default false
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_strip_nulls(jsonb_build_object(
    'reference', conversation.public_reference,
    'status', 'received',
    'created_at', conversation.created_at,
    'replayed', $2,
    'selected_work_count', (
      select count(*)::integer from public.conversation_works work
      where work.conversation_id = conversation.id
    ),
    'conversation_id', case
      when conversation.initiator_user_id is not null then conversation.id
    end
  ))
  from public.conversation_messages message
  join public.conversations conversation on conversation.id = message.conversation_id
  where message.id = $1 and message.is_initial
$$;

create or replace function public.create_project_inquiry(
  sender_name text,
  sender_email text,
  inquiry_type text,
  organization text,
  project_use text,
  timeline text,
  budget_range text,
  message_body text,
  website text,
  work_ids uuid[],
  idempotency_key uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  provider_user_id uuid := auth.uid();
  actor_id uuid;
  actor_role public.role_code;
  actor_status public.account_status;
  actor_email text;
  normalized_name text := btrim(coalesce(sender_name, ''));
  normalized_email text := lower(btrim(coalesce(sender_email, '')));
  normalized_type text := lower(btrim(coalesce(inquiry_type, '')));
  normalized_organization text := nullif(btrim(coalesce(organization, '')), '');
  normalized_project_use text := btrim(coalesce(project_use, ''));
  normalized_timeline text := nullif(btrim(coalesce(timeline, '')), '');
  normalized_budget text := nullif(btrim(coalesce(budget_range, '')), '');
  normalized_message text := btrim(coalesce(message_body, ''));
  normalized_works uuid[] := '{}'::uuid[];
  request_key uuid := idempotency_key;
  request_hash char(64);
  rate_key char(64);
  recipient_id uuid;
  new_conversation_id uuid := gen_random_uuid();
  new_message_id uuid := gen_random_uuid();
  created_at_value timestamptz := clock_timestamp();
  existing_message public.conversation_messages%rowtype;
  eligible_work_count integer;
  work_owner_count integer;
  recent_request_count integer;
  global_request_count integer;
  recipient_request_count integer;
begin
  if nullif(btrim(coalesce(website, '')), '') is not null then
    return public.communications_error(
      'INQUIRY_REJECTED', 'The inquiry could not be accepted.'
    );
  end if;
  if request_key is null
     or length(normalized_name) not between 1 and 120
     or normalized_name ~ '[[:cntrl:]]'
     or length(normalized_email) not between 3 and 180
     or normalized_email !~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$'
     or normalized_email ~ '[[:cntrl:]]'
     or normalized_type not in (
       'exhibition', 'editorial', 'licensing', 'print', 'commission', 'other'
     )
     or coalesce(length(normalized_organization), 0) > 180
     or coalesce(normalized_organization ~ '[[:cntrl:]]', false)
     or length(normalized_project_use) not between 5 and 280
     or normalized_project_use ~ '[[:cntrl:]]'
     or coalesce(length(normalized_timeline), 0) > 120
     or coalesce(normalized_timeline ~ '[[:cntrl:]]', false)
     or coalesce(length(normalized_budget), 0) > 120
     or coalesce(normalized_budget ~ '[[:cntrl:]]', false)
     or length(normalized_message) not between 10 and 5000
     or regexp_replace(normalized_message, E'[\\t\\n\\r]', '', 'g')
       ~ '[[:cntrl:]]' then
    return public.communications_error(
      'INQUIRY_VALIDATION_FAILED', 'Review the inquiry fields and try again.'
    );
  end if;

  select coalesce(array_agg(distinct work_id order by work_id), '{}'::uuid[])
  into normalized_works
  from unnest(coalesce(work_ids, '{}'::uuid[])) work_id;
  if cardinality(coalesce(work_ids, '{}'::uuid[])) > 10
     or cardinality(coalesce(work_ids, '{}'::uuid[])) <> cardinality(normalized_works)
     or array_position(coalesce(work_ids, '{}'::uuid[]), null) is not null then
    return public.communications_error(
      'INQUIRY_WORKS_INVALID', 'Select up to 10 distinct published works.'
    );
  end if;

  if provider_user_id is not null then
    if public.is_recovery_auth_session() then
      return public.communications_error(
        'COMMUNICATION_ACCOUNT_RESTRICTED', 'This session cannot create an inquiry.'
      );
    end if;
    actor_id := public.current_app_user_id();
    select target.account_status, target.email_normalized
    into actor_status, actor_email
    from public.users target where target.id = actor_id;
    if actor_id is null or actor_status <> 'active'::public.account_status then
      return public.communications_error(
        'COMMUNICATION_ACCOUNT_RESTRICTED', 'This account cannot create an inquiry.'
      );
    end if;
    if normalized_email <> actor_email then
      return public.communications_error(
        'INQUIRY_VALIDATION_FAILED', 'Use the email address for the signed-in account.'
      );
    end if;
    select role_row.role into actor_role
    from public.user_roles role_row
    where role_row.user_id = actor_id
    order by case role_row.role
      when 'super_admin'::public.role_code then 1
      when 'admin'::public.role_code then 2
      when 'reviewer'::public.role_code then 3
      else 4 end
    limit 1;
  end if;

  request_hash := encode(extensions.digest(convert_to(jsonb_build_object(
    'actor_id', actor_id,
    'sender_name', normalized_name,
    'sender_email', normalized_email,
    'inquiry_type', normalized_type,
    'organization', normalized_organization,
    'project_use', normalized_project_use,
    'timeline', normalized_timeline,
    'budget_range', normalized_budget,
    'message', normalized_message,
    'work_ids', to_jsonb(normalized_works)
  )::text, 'UTF8'), 'sha256'), 'hex');
  rate_key := encode(extensions.digest(convert_to(
    case when actor_id is null then 'guest:' || normalized_email
         else 'member:' || actor_id::text end,
    'UTF8'), 'sha256'), 'hex');

  perform pg_advisory_xact_lock(
    hashtextextended('mt-project-inquiry-key:' || request_key::text, 0)
  );
  select * into existing_message
  from public.conversation_messages message
  where message.idempotency_key = request_key;
  if existing_message.id is not null then
    if existing_message.is_initial
       and existing_message.request_fingerprint = request_hash then
      return public.project_inquiry_result(existing_message.id, true);
    end if;
    return public.communications_error(
      'INQUIRY_IDEMPOTENCY_CONFLICT',
      'This idempotency key is already bound to another request.'
    );
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended('mt-project-inquiry-rate:' || rate_key, 0)
  );
  select count(*)::integer into recent_request_count
  from public.conversations conversation
  where conversation.rate_limit_key = rate_key
    and conversation.created_at >= now() - interval '1 hour';
  if recent_request_count >= 5 then
    return public.communications_error(
      'INQUIRY_RATE_LIMITED', 'Too many recent inquiries. Try again later.'
    );
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended('mt-project-inquiry-global-hourly', 0)
  );
  select count(*)::integer into global_request_count
  from public.conversations conversation
  where conversation.created_at >= now() - interval '1 hour';
  if global_request_count >= 500 then
    return public.communications_error(
      'INQUIRY_RATE_LIMITED', 'Too many recent inquiries. Try again later.'
    );
  end if;

  if cardinality(normalized_works) > 0 then
    select
      count(*)::integer,
      count(distinct image.owner_user_id)::integer,
      (array_agg(distinct image.owner_user_id))[1]
    into eligible_work_count, work_owner_count, recipient_id
    from public.images image
    join public.users owner on owner.id = image.owner_user_id
    where image.id = any(normalized_works)
      and image.deleted_at is null
      and image.processing_status = 'ready'::public.processing_status
      and image.workflow_status = 'approved'::public.workflow_status
      and image.publication_status = 'published'::public.publication_status
      and image.published_at is not null
      and image.unpublished_at is null
      and owner.account_status = 'active'::public.account_status
      and not owner.is_system_identity;
    if eligible_work_count <> cardinality(normalized_works)
       or work_owner_count <> 1 then
      return public.communications_error(
        'INQUIRY_WORKS_INVALID',
        'Selected works must be published and belong to one recipient.'
      );
    end if;
  else
    select creator.id into recipient_id
    from public.users creator
    join public.user_profiles profile on profile.user_id = creator.id
    where creator.account_status = 'active'::public.account_status
      and not creator.is_system_identity
      and profile.public_slug is not null
      and creator.id is distinct from actor_id
      and exists (
        select 1 from public.images image
        where image.owner_user_id = creator.id
          and image.deleted_at is null
          and image.processing_status = 'ready'::public.processing_status
          and image.workflow_status = 'approved'::public.workflow_status
          and image.publication_status = 'published'::public.publication_status
          and image.published_at is not null
          and image.unpublished_at is null
      )
    order by profile.public_slug, creator.id
    limit 1;
    if recipient_id is null then
      select administrator.id into recipient_id
      from public.users administrator
      join public.user_roles role_row on role_row.user_id = administrator.id
      where administrator.account_status = 'active'::public.account_status
        and not administrator.is_system_identity
        and administrator.id is distinct from actor_id
        and role_row.role = 'super_admin'::public.role_code
      order by administrator.created_at, administrator.id
      limit 1;
    end if;
  end if;

  if recipient_id is null then
    return public.communications_error(
      'INQUIRY_RECIPIENT_UNAVAILABLE', 'No inquiry recipient is currently available.'
    );
  end if;
  if recipient_id = actor_id then
    return public.communications_error(
      'INQUIRY_SELF_FORBIDDEN', 'An inquiry cannot be sent to the same account.'
    );
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended('mt-project-inquiry-recipient-hourly:' || recipient_id::text, 0)
  );
  select count(*)::integer into recipient_request_count
  from public.conversations conversation
  where conversation.recipient_user_id = recipient_id
    and conversation.created_at >= now() - interval '1 hour';
  if recipient_request_count >= 100 then
    return public.communications_error(
      'INQUIRY_RATE_LIMITED', 'Too many recent inquiries. Try again later.'
    );
  end if;

  insert into public.conversations (
    id, public_reference, recipient_user_id, initiator_user_id,
    sender_name, sender_email, inquiry_type, organization, project_use,
    timeline, budget_range, status, version, rate_limit_key,
    request_fingerprint, idempotency_key, last_message_at, created_at, updated_at
  ) values (
    new_conversation_id,
    'INQ-' || upper(substr(replace(new_conversation_id::text, '-', ''), 1, 12)),
    recipient_id, actor_id, normalized_name, normalized_email,
    normalized_type, normalized_organization, normalized_project_use,
    normalized_timeline, normalized_budget, 'open', 1, rate_key,
    request_hash, request_key, created_at_value, created_at_value, created_at_value
  );

  insert into public.conversation_participants (
    conversation_id, user_id, participant_role, joined_at
  ) values (
    new_conversation_id, recipient_id, 'recipient', created_at_value
  );
  if actor_id is not null then
    insert into public.conversation_participants (
      conversation_id, user_id, participant_role, joined_at
    ) values (
      new_conversation_id, actor_id, 'sender', created_at_value
    );
  end if;

  insert into public.conversation_works (
    conversation_id, image_id, owner_user_id, position, created_at
  )
  select new_conversation_id, image.id, image.owner_user_id,
         work.position::integer, created_at_value
  from unnest(normalized_works) with ordinality work(image_id, position)
  join public.images image on image.id = work.image_id;

  insert into public.conversation_messages (
    id, conversation_id, sender_user_id, sender_kind, sender_display_name,
    body, delivery_status, is_initial, expected_conversation_version,
    result_conversation_version, request_fingerprint, idempotency_key, created_at
  ) values (
    new_message_id, new_conversation_id, actor_id,
    case when actor_id is null then 'guest' else 'member' end,
    normalized_name, normalized_message, 'recorded', true, null, 1,
    request_hash, request_key, created_at_value
  );

  update public.conversation_participants participant set
    last_read_message_id = new_message_id,
    last_read_at = created_at_value
  where participant.conversation_id = new_conversation_id
    and participant.user_id = actor_id;

  insert into public.notifications (recipient_user_id, type, payload)
  values (recipient_id, 'project_inquiry_received', jsonb_build_object(
    'conversation_id', new_conversation_id,
    'message_id', new_message_id,
    'inquiry_type', normalized_type,
    'work_count', cardinality(normalized_works),
    'status', 'open'
  ));

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    actor_id, actor_role, 'project.inquiry_created', 'conversation',
    new_conversation_id::text, request_key::text, 'project_inquiry', null,
    jsonb_build_object(
      'conversation_id', new_conversation_id,
      'status', 'open',
      'sender_kind', case when actor_id is null then 'guest' else 'member' end,
      'inquiry_type', normalized_type,
      'work_count', cardinality(normalized_works),
      'message_id', new_message_id
    ), 'mt-communications-2026-07-v1', 'success'
  );

  return public.project_inquiry_result(new_message_id, false);
end;
$$;

create or replace function public.list_my_conversations(
  status_filter text default 'all',
  page_limit integer default 30,
  cursor_last_message_at timestamptz default null,
  cursor_id uuid default null
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  normalized_status text := lower(btrim(coalesce(status_filter, 'all')));
  item_rows jsonb;
  candidate_count integer;
  next_last_message_at timestamptz;
  next_id uuid;
begin
  actor_id := public.communications_require_actor(true);
  if normalized_status not in ('all', 'open', 'replied', 'closed') then
    return public.communications_error(
      'CONVERSATION_FILTER_INVALID', 'Choose a supported conversation status.'
    );
  end if;
  if page_limit is null or page_limit not between 1 and 100 then
    return public.communications_error(
      'CONVERSATION_PAGE_INVALID', 'Use a conversation page size from 1 to 100.'
    );
  end if;
  if (cursor_last_message_at is null) <> (cursor_id is null) then
    return public.communications_error(
      'CONVERSATION_CURSOR_INVALID', 'Use a complete conversation cursor.'
    );
  end if;

  with candidates as (
    select conversation.id, conversation.last_message_at,
           row_number() over (
             order by conversation.last_message_at desc, conversation.id desc
           ) as row_number
    from public.conversations conversation
    join public.conversation_participants participant
      on participant.conversation_id = conversation.id
     and participant.user_id = actor_id
    where (normalized_status = 'all' or conversation.status = normalized_status)
      and (
        cursor_last_message_at is null
        or (conversation.last_message_at, conversation.id)
          < (cursor_last_message_at, cursor_id)
      )
    order by conversation.last_message_at desc, conversation.id desc
    limit page_limit + 1
  )
  select
    coalesce(jsonb_agg(
      public.conversation_summary_json(candidate.id, actor_id)
      order by candidate.row_number
    ) filter (where candidate.row_number <= page_limit), '[]'::jsonb),
    count(*)::integer,
    max(candidate.last_message_at) filter (where candidate.row_number = page_limit),
    (max(candidate.id::text) filter (where candidate.row_number = page_limit))::uuid
  into item_rows, candidate_count, next_last_message_at, next_id
  from candidates candidate;

  return jsonb_build_object(
    'items', item_rows,
    'pagination', jsonb_build_object(
      'limit', page_limit,
      'has_more', candidate_count > page_limit,
      'next_cursor', case when candidate_count > page_limit then jsonb_build_object(
        'last_message_at', next_last_message_at,
        'id', next_id
      ) else null end
    )
  );
end;
$$;

create or replace function public.get_my_conversation(
  target_conversation_id uuid,
  page_limit integer default 100,
  cursor_created_at timestamptz default null,
  cursor_id uuid default null
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  summary jsonb;
  participant_rows jsonb;
  message_rows jsonb;
  candidate_count integer;
  next_created_at timestamptz;
  next_id uuid;
begin
  actor_id := public.communications_require_actor(true);
  if page_limit is null or page_limit not between 1 and 200 then
    return public.communications_error(
      'CONVERSATION_PAGE_INVALID', 'Use a message page size from 1 to 200.'
    );
  end if;
  if (cursor_created_at is null) <> (cursor_id is null) then
    return public.communications_error(
      'CONVERSATION_CURSOR_INVALID', 'Use a complete message cursor.'
    );
  end if;
  summary := public.conversation_summary_json(target_conversation_id, actor_id);
  if summary is null then
    return public.communications_error(
      'CONVERSATION_NOT_FOUND', 'The conversation is unavailable.'
    );
  end if;

  select coalesce(jsonb_agg(jsonb_build_object(
    'participant_role', participant.participant_role,
    'display_name', coalesce(
      profile.display_name, nullif(split_part(account.email, '@', 1), ''), 'Member'
    ),
    'email', account.email,
    'last_read_message_id', participant.last_read_message_id,
    'last_read_at', participant.last_read_at,
    'joined_at', participant.joined_at
  ) order by participant.participant_role, participant.user_id), '[]'::jsonb)
  into participant_rows
  from public.conversation_participants participant
  join public.users account on account.id = participant.user_id
  left join public.user_profiles profile on profile.user_id = account.id
  where participant.conversation_id = target_conversation_id;

  with candidates as (
    select message.id, message.created_at,
           row_number() over (
             order by message.created_at desc, message.id desc
           ) as row_number
    from public.conversation_messages message
    where message.conversation_id = target_conversation_id
      and (
        cursor_created_at is null
        or (message.created_at, message.id) < (cursor_created_at, cursor_id)
      )
    order by message.created_at desc, message.id desc
    limit page_limit + 1
  )
  select
    coalesce(jsonb_agg(
      public.conversation_message_json(candidate.id)
      order by candidate.created_at, candidate.id
    ) filter (where candidate.row_number <= page_limit), '[]'::jsonb),
    count(*)::integer,
    max(candidate.created_at) filter (where candidate.row_number = page_limit),
    (max(candidate.id::text) filter (where candidate.row_number = page_limit))::uuid
  into message_rows, candidate_count, next_created_at, next_id
  from candidates candidate;

  return jsonb_build_object(
    'conversation', summary,
    'participants', participant_rows,
    'messages', message_rows,
    'pagination', jsonb_build_object(
      'limit', page_limit,
      'has_more', candidate_count > page_limit,
      'next_cursor', case when candidate_count > page_limit then jsonb_build_object(
        'created_at', next_created_at,
        'id', next_id
      ) else null end
    )
  );
end;
$$;

create or replace function public.conversation_reply_result(
  reply_message_id uuid,
  replayed boolean default false
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'conversation_id', conversation.id,
    'message', public.conversation_message_json(message.id),
    'conversation_version', message.result_conversation_version,
    'status', case
      when message.sender_user_id = conversation.recipient_user_id then 'replied'
      else 'open'
    end,
    'delivery', jsonb_build_object(
      'record_status', 'recorded',
      'provider_status', case message.delivery_status
        when 'provider_unavailable' then 'unavailable'
        else 'not_required'
      end,
      'provider_action_required', message.delivery_status = 'provider_unavailable'
    ),
    'replayed', $2
  )
  from public.conversation_messages message
  join public.conversations conversation on conversation.id = message.conversation_id
  where message.id = $1 and not message.is_initial
$$;

create or replace function public.reply_to_conversation(
  target_conversation_id uuid,
  expected_version integer,
  message_body text,
  idempotency_key uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_role public.role_code;
  actor_name text;
  participant public.conversation_participants%rowtype;
  conversation public.conversations%rowtype;
  normalized_message text := btrim(coalesce(message_body, ''));
  request_key uuid := idempotency_key;
  request_hash char(64);
  existing_message public.conversation_messages%rowtype;
  new_message_id uuid := gen_random_uuid();
  created_at_value timestamptz := clock_timestamp();
  next_status text;
  previous_status text;
  delivery_status_value text;
begin
  actor_id := public.communications_require_actor(true);
  if request_key is null
     or expected_version is null or expected_version <= 0
     or length(normalized_message) not between 1 and 5000
     or regexp_replace(normalized_message, E'[\\t\\n\\r]', '', 'g')
       ~ '[[:cntrl:]]' then
    return public.communications_error(
      'CONVERSATION_MESSAGE_INVALID',
      'A message, current version, and UUID idempotency key are required.'
    );
  end if;
  request_hash := encode(extensions.digest(convert_to(jsonb_build_object(
    'conversation_id', target_conversation_id,
    'actor_id', actor_id,
    'expected_version', expected_version,
    'message', normalized_message
  )::text, 'UTF8'), 'sha256'), 'hex');

  perform pg_advisory_xact_lock(
    hashtextextended('mt-conversation-reply-key:' || request_key::text, 0)
  );
  select * into existing_message
  from public.conversation_messages message
  where message.idempotency_key = request_key;
  if existing_message.id is not null then
    if not existing_message.is_initial
       and existing_message.sender_user_id = actor_id
       and existing_message.conversation_id = target_conversation_id
       and existing_message.expected_conversation_version = expected_version
       and existing_message.request_fingerprint = request_hash then
      return public.conversation_reply_result(existing_message.id, true);
    end if;
    return public.communications_error(
      'CONVERSATION_IDEMPOTENCY_CONFLICT',
      'This idempotency key is already bound to another message.'
    );
  end if;

  select * into conversation
  from public.conversations target
  where target.id = target_conversation_id
  for update;
  if conversation.id is null then
    return public.communications_error(
      'CONVERSATION_NOT_FOUND', 'The conversation is unavailable.'
    );
  end if;
  select * into participant
  from public.conversation_participants target
  where target.conversation_id = conversation.id
    and target.user_id = actor_id;
  if participant.user_id is null then
    return public.communications_error(
      'CONVERSATION_NOT_FOUND', 'The conversation is unavailable.'
    );
  end if;
  if conversation.version <> expected_version then
    return public.communications_error(
      'CONVERSATION_VERSION_CONFLICT',
      'This conversation changed. Reload before replying.'
    );
  end if;
  if conversation.status = 'closed' then
    return public.communications_error(
      'CONVERSATION_STATE_CONFLICT', 'A closed conversation cannot accept replies.'
    );
  end if;

  select coalesce(
    profile.display_name, nullif(split_part(account.email, '@', 1), ''), 'Member'
  ) into actor_name
  from public.users account
  left join public.user_profiles profile on profile.user_id = account.id
  where account.id = actor_id;
  select role_row.role into actor_role
  from public.user_roles role_row
  where role_row.user_id = actor_id
  order by case role_row.role
    when 'super_admin'::public.role_code then 1
    when 'admin'::public.role_code then 2
    when 'reviewer'::public.role_code then 3
    else 4 end
  limit 1;

  next_status := case participant.participant_role
    when 'recipient' then 'replied' else 'open' end;
  previous_status := conversation.status;
  delivery_status_value := case
    when participant.participant_role = 'recipient'
     and conversation.initiator_user_id is null then 'provider_unavailable'
    else 'recorded'
  end;

  update public.conversations target set
    status = next_status,
    version = target.version + 1,
    last_message_at = created_at_value,
    updated_at = created_at_value
  where target.id = conversation.id
  returning * into conversation;

  insert into public.conversation_messages (
    id, conversation_id, sender_user_id, sender_kind, sender_display_name,
    body, delivery_status, is_initial, expected_conversation_version,
    result_conversation_version, request_fingerprint, idempotency_key, created_at
  ) values (
    new_message_id, conversation.id, actor_id, 'member', actor_name,
    normalized_message, delivery_status_value, false, expected_version,
    conversation.version, request_hash, request_key, created_at_value
  );

  update public.conversation_participants target set
    last_read_message_id = new_message_id,
    last_read_at = created_at_value
  where target.conversation_id = conversation.id
    and target.user_id = actor_id;

  insert into public.notifications (recipient_user_id, type, payload)
  select target.user_id, 'conversation_reply_received', jsonb_build_object(
    'conversation_id', conversation.id,
    'message_id', new_message_id,
    'status', next_status,
    'provider_action_required', false
  )
  from public.conversation_participants target
  where target.conversation_id = conversation.id
    and target.user_id <> actor_id;

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    actor_id, actor_role,
    case when delivery_status_value = 'provider_unavailable'
      then 'conversation.reply_guest_delivery_unavailable'
      else 'conversation.reply_recorded' end,
    'conversation', conversation.id::text, request_key::text, 'participant_reply',
    jsonb_build_object(
      'conversation_id', conversation.id,
      'status', previous_status,
      'version', expected_version
    ),
    jsonb_build_object(
      'conversation_id', conversation.id,
      'message_id', new_message_id,
      'status', next_status,
      'version', conversation.version,
      'provider_action_required', delivery_status_value = 'provider_unavailable'
    ),
    'mt-communications-2026-07-v1', 'success'
  );

  return public.conversation_reply_result(new_message_id, false);
end;
$$;

create or replace function public.conversation_status_result(
  status_action_id uuid,
  replayed boolean default false
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select action.result_snapshot || jsonb_build_object('replayed', $2)
  from public.conversation_status_actions action
  where action.id = $1
$$;

create or replace function public.set_my_conversation_status(
  target_conversation_id uuid,
  expected_version integer,
  target_status text,
  idempotency_key uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_role public.role_code;
  participant public.conversation_participants%rowtype;
  conversation public.conversations%rowtype;
  existing_action public.conversation_status_actions%rowtype;
  normalized_status text := lower(btrim(coalesce(target_status, '')));
  request_key uuid := idempotency_key;
  request_hash char(64);
  action_id uuid := gen_random_uuid();
  action_created_at timestamptz := clock_timestamp();
  delivery_status_value text;
  result_snapshot jsonb;
  previous_status text;
begin
  actor_id := public.communications_require_actor(true);
  if target_conversation_id is null
     or expected_version is null or expected_version <= 0
     or request_key is null
     or normalized_status not in ('open', 'closed') then
    return public.communications_error(
      'CONVERSATION_STATUS_INVALID',
      'A conversation, current version, target status, and UUID key are required.'
    );
  end if;
  request_hash := encode(extensions.digest(convert_to(jsonb_build_object(
    'conversation_id', target_conversation_id,
    'actor_id', actor_id,
    'expected_version', expected_version,
    'target_status', normalized_status
  )::text, 'UTF8'), 'sha256'), 'hex');

  perform pg_advisory_xact_lock(
    hashtextextended('mt-conversation-status-key:' || request_key::text, 0)
  );
  select * into existing_action
  from public.conversation_status_actions action
  where action.idempotency_key = request_key;
  if existing_action.id is not null then
    if existing_action.actor_user_id = actor_id
       and existing_action.conversation_id = target_conversation_id
       and existing_action.expected_conversation_version = expected_version
       and existing_action.request_fingerprint = request_hash then
      return public.conversation_status_result(existing_action.id, true);
    end if;
    return public.communications_error(
      'CONVERSATION_IDEMPOTENCY_CONFLICT',
      'This idempotency key is already bound to another status change.'
    );
  end if;

  select * into conversation
  from public.conversations target
  where target.id = target_conversation_id
  for update;
  if conversation.id is null then
    return public.communications_error(
      'CONVERSATION_NOT_FOUND', 'The conversation is unavailable.'
    );
  end if;
  select * into participant
  from public.conversation_participants target
  where target.conversation_id = conversation.id
    and target.user_id = actor_id
    and target.participant_role = 'recipient';
  if participant.user_id is null then
    return public.communications_error(
      'CONVERSATION_NOT_FOUND', 'The conversation is unavailable.'
    );
  end if;
  if conversation.version <> expected_version then
    return public.communications_error(
      'CONVERSATION_VERSION_CONFLICT',
      'This conversation changed. Reload before updating its status.'
    );
  end if;
  if normalized_status = conversation.status
     or (normalized_status = 'open' and conversation.status <> 'closed')
     or (
       normalized_status = 'closed'
       and conversation.status not in ('open', 'replied')
     ) then
    return public.communications_error(
      'CONVERSATION_STATE_CONFLICT',
      'The requested conversation status transition is unavailable.'
    );
  end if;

  previous_status := conversation.status;
  delivery_status_value := case
    when conversation.initiator_user_id is null then 'provider_unavailable'
    else 'recorded'
  end;
  select role_row.role into actor_role
  from public.user_roles role_row
  where role_row.user_id = actor_id
  order by case role_row.role
    when 'super_admin'::public.role_code then 1
    when 'admin'::public.role_code then 2
    when 'reviewer'::public.role_code then 3
    else 4 end
  limit 1;

  update public.conversations target set
    status = normalized_status,
    version = target.version + 1,
    updated_at = action_created_at
  where target.id = conversation.id
  returning * into conversation;

  result_snapshot := jsonb_build_object(
    'conversation_id', conversation.id,
    'status', conversation.status,
    'conversation_version', conversation.version,
    'delivery', jsonb_build_object(
      'record_status', 'recorded',
      'provider_status', case delivery_status_value
        when 'provider_unavailable' then 'unavailable'
        else 'not_required'
      end,
      'provider_action_required', delivery_status_value = 'provider_unavailable'
    ),
    'replayed', false
  );

  insert into public.conversation_status_actions (
    id, conversation_id, actor_user_id, target_status,
    expected_conversation_version, result_conversation_version,
    delivery_status, request_fingerprint, idempotency_key,
    result_snapshot, created_at
  ) values (
    action_id, conversation.id, actor_id, conversation.status,
    expected_version, conversation.version, delivery_status_value,
    request_hash, request_key, result_snapshot, action_created_at
  );

  if conversation.initiator_user_id is not null then
    insert into public.notifications (recipient_user_id, type, payload)
    values (
      conversation.initiator_user_id,
      'conversation_status_changed',
      jsonb_build_object(
        'conversation_id', conversation.id,
        'status', conversation.status,
        'provider_action_required', false
      )
    );
  end if;

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    actor_id, actor_role,
    case conversation.status when 'closed' then 'conversation.closed'
      else 'conversation.reopened' end,
    'conversation', conversation.id::text, request_key::text,
    case conversation.status when 'closed' then 'recipient_close'
      else 'recipient_reopen' end,
    jsonb_build_object('status', previous_status, 'version', expected_version),
    jsonb_build_object(
      'status', conversation.status,
      'version', conversation.version,
      'provider_action_required', delivery_status_value = 'provider_unavailable'
    ),
    'mt-communications-2026-07-v1', 'success'
  );

  return public.conversation_status_result(action_id, false);
end;
$$;

create or replace function public.mark_my_conversation_read(
  target_conversation_id uuid,
  target_message_id uuid default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  participant public.conversation_participants%rowtype;
  target_message public.conversation_messages%rowtype;
  unread_count integer;
begin
  actor_id := public.communications_require_actor(true);
  select * into participant
  from public.conversation_participants target
  where target.conversation_id = target_conversation_id
    and target.user_id = actor_id
  for update;
  if participant.user_id is null then
    return public.communications_error(
      'CONVERSATION_NOT_FOUND', 'The conversation is unavailable.'
    );
  end if;

  if target_message_id is null then
    select * into target_message
    from public.conversation_messages message
    where message.conversation_id = target_conversation_id
    order by message.created_at desc, message.id desc
    limit 1;
  else
    select * into target_message
    from public.conversation_messages message
    where message.id = target_message_id
      and message.conversation_id = target_conversation_id;
  end if;
  if target_message.id is null then
    return public.communications_error(
      'CONVERSATION_READ_TARGET_INVALID', 'The read target is unavailable.'
    );
  end if;

  if participant.last_read_at is null
     or (target_message.created_at, target_message.id)
       > (participant.last_read_at, participant.last_read_message_id) then
    update public.conversation_participants target set
      last_read_message_id = target_message.id,
      last_read_at = target_message.created_at
    where target.conversation_id = target_conversation_id
      and target.user_id = actor_id
    returning * into participant;
  end if;

  select count(*)::integer into unread_count
  from public.conversation_messages message
  where message.conversation_id = target_conversation_id
    and message.sender_user_id is distinct from actor_id
    and (
      participant.last_read_at is null
      or (message.created_at, message.id)
        > (participant.last_read_at, participant.last_read_message_id)
    );
  return jsonb_build_object(
    'conversation_id', target_conversation_id,
    'last_read_message_id', participant.last_read_message_id,
    'last_read_at', participant.last_read_at,
    'unread_count', unread_count
  );
end;
$$;

create or replace function public.audit_safe_state(state jsonb)
returns jsonb
language sql
immutable
set search_path = ''
as $$
  select case when jsonb_typeof($1) = 'object' then
    jsonb_strip_nulls(jsonb_build_object(
      'status', $1 -> 'status',
      'workflow_status', $1 -> 'workflow_status',
      'publication_status', $1 -> 'publication_status',
      'processing_status', $1 -> 'processing_status',
      'submission_status', $1 -> 'submission_status',
      'account_status', $1 -> 'account_status',
      'version', $1 -> 'version',
      'image_version', $1 -> 'image_version',
      'user_version', $1 -> 'user_version',
      'action', $1 -> 'action',
      'decision', $1 -> 'decision',
      'reason_code', $1 -> 'reason_code',
      'error_code', $1 -> 'error_code',
      'target_role', $1 -> 'target_role',
      'provider_action_required', $1 -> 'provider_action_required'
    ))
  else '{}'::jsonb end
$$;

create or replace function public.admin_audit_actor_json(actor_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', $1,
    'roles', coalesce((
      select jsonb_agg(role_row.role order by role_row.role)
      from public.user_roles role_row
      where role_row.user_id = $1
        and role_row.role in ('admin'::public.role_code, 'super_admin'::public.role_code)
    ), '[]'::jsonb)
  )
$$;

create or replace function public.admin_audit_summary_json(target_audit_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', audit.id,
    'target_type', case
      when audit.target_type ~ '^[a-z0-9_]{1,64}$' then audit.target_type
      else 'redacted'
    end,
    'target_id', case
      when audit.target_id ~ '^[A-Za-z0-9:_-]{1,180}$' then audit.target_id
      else 'redacted'
    end,
    'actor', jsonb_build_object(
      'id', audit.actor_user_id,
      'display_name', case when audit.actor_user_id is null then 'Guest/System'
        else coalesce(actor_profile.display_name, 'Account') end,
      'role', audit.actor_role
    ),
    'action', case
      when audit.action ~ '^[a-z0-9][a-z0-9._-]{0,119}$' then audit.action
      else 'redacted'
    end,
    'request_id', case
      when audit.request_id ~ '^[A-Za-z0-9:_-]{1,180}$' then audit.request_id
      else 'redacted'
    end,
    'reason_code', case
      when audit.reason_code is null then null
      when audit.reason_code ~ '^[a-z0-9][a-z0-9._-]{0,119}$' then audit.reason_code
      else 'redacted'
    end,
    'result', audit.result,
    'policy_version', case
      when audit.policy_version is null then null
      when audit.policy_version ~ '^[A-Za-z0-9._-]{1,120}$' then audit.policy_version
      else 'redacted'
    end,
    'created_at', audit.created_at
  )
  from public.audit_logs audit
  left join public.user_profiles actor_profile
    on actor_profile.user_id = audit.actor_user_id
  where audit.id = $1
$$;

drop function if exists public.admin_list_audit_logs(
  text, text, text, integer, timestamptz, uuid
);
create or replace function public.admin_list_audit_logs(
  result_filter text default 'all',
  target_type_filter text default 'all',
  action_filter text default '',
  actor_filter text default 'all',
  request_id_filter text default '',
  created_from timestamptz default (now() - interval '30 days'),
  created_to timestamptz default now(),
  page_limit integer default 50,
  cursor_created_at timestamptz default null,
  cursor_id uuid default null
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  normalized_result text := lower(btrim(coalesce(result_filter, 'all')));
  normalized_target text := lower(btrim(coalesce(target_type_filter, 'all')));
  normalized_action text := lower(btrim(coalesce(action_filter, '')));
  normalized_actor text := lower(btrim(coalesce(actor_filter, 'all')));
  normalized_request text := btrim(coalesce(request_id_filter, ''));
  normalized_actor_id uuid;
  item_rows jsonb;
  candidate_count integer;
  next_created_at timestamptz;
  next_id uuid;
begin
  actor_id := public.admin_require_user_governance_actor();
  if normalized_result not in ('all', 'success', 'failure')
     or (normalized_target <> 'all' and normalized_target !~ '^[a-z0-9_]{1,64}$')
     or (normalized_action <> '' and normalized_action !~ '^[a-z0-9][a-z0-9._-]{0,99}$')
     or (normalized_actor <> 'all' and normalized_actor !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
     or (normalized_request <> '' and normalized_request !~ '^[A-Za-z0-9:_-]{1,180}$') then
    return public.communications_error('AUDIT_FILTER_INVALID', 'Choose supported audit filters.');
  end if;
  if created_from is null or created_to is null or created_from > created_to
     or created_to - created_from > interval '366 days'
     or created_to > clock_timestamp() + interval '5 minutes' then
    return public.communications_error('AUDIT_DATE_RANGE_INVALID', 'Choose a date range of at most 366 days.');
  end if;
  if normalized_actor <> 'all' then
    normalized_actor_id := normalized_actor::uuid;
  end if;
  if page_limit is null or page_limit not between 1 and 100 then
    return public.communications_error('AUDIT_PAGE_INVALID', 'Use an audit page size from 1 to 100.');
  end if;
  if (cursor_created_at is null) <> (cursor_id is null) then
    return public.communications_error('AUDIT_CURSOR_INVALID', 'Use a complete audit cursor.');
  end if;

  with candidates as (
    select audit.id, audit.created_at,
           row_number() over (order by audit.created_at desc, audit.id desc) as row_number
    from public.audit_logs audit
    where audit.created_at between created_from and created_to
      and (normalized_result = 'all' or audit.result = normalized_result)
      and (normalized_target = 'all' or audit.target_type = normalized_target)
      and (normalized_action = '' or position(normalized_action in lower(audit.action)) = 1)
      and (normalized_actor_id is null or audit.actor_user_id = normalized_actor_id)
      and (normalized_request = '' or position(normalized_request in audit.request_id) = 1)
      and (cursor_created_at is null or (audit.created_at, audit.id) < (cursor_created_at, cursor_id))
    order by audit.created_at desc, audit.id desc
    limit page_limit + 1
  )
  select coalesce(jsonb_agg(
      public.admin_audit_summary_json(candidate.id) order by candidate.row_number
    ) filter (where candidate.row_number <= page_limit), '[]'::jsonb),
    count(*)::integer,
    max(candidate.created_at) filter (where candidate.row_number = page_limit),
    (max(candidate.id::text) filter (where candidate.row_number = page_limit))::uuid
  into item_rows, candidate_count, next_created_at, next_id
  from candidates candidate;

  return jsonb_build_object(
    'actor', public.admin_audit_actor_json(actor_id),
    'items', item_rows,
    'pagination', jsonb_build_object(
      'limit', page_limit,
      'has_more', candidate_count > page_limit,
      'next_cursor', case when candidate_count > page_limit then jsonb_build_object(
        'created_at', next_created_at, 'id', next_id
      ) else null end
    )
  );
end;
$$;

create or replace function public.admin_get_audit_log(target_audit_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  audit public.audit_logs%rowtype;
  summary jsonb;
  safe_before jsonb;
  safe_after jsonb;
  changed_fields jsonb;
begin
  actor_id := public.admin_require_user_governance_actor();
  select * into audit from public.audit_logs row where row.id = target_audit_id;
  if audit.id is null then
    return public.communications_error(
      'AUDIT_NOT_FOUND', 'The audit event is unavailable.'
    );
  end if;
  summary := public.admin_audit_summary_json(audit.id);
  safe_before := public.audit_safe_state(audit.before_state);
  safe_after := public.audit_safe_state(audit.after_state);
  select coalesce(jsonb_agg(field order by field), '[]'::jsonb)
  into changed_fields
  from (
    select field
    from jsonb_object_keys(safe_before || safe_after) field
    where safe_before -> field is distinct from safe_after -> field
  ) changed;
  return jsonb_build_object(
    'actor', public.admin_audit_actor_json(actor_id),
    'audit', summary || jsonb_build_object(
      'changes', jsonb_build_object(
        'before', safe_before,
        'after', safe_after,
        'changed_fields', changed_fields
      )
    )
  );
end;
$$;

create or replace function public.admin_audit_export_result(
  export_action_id uuid,
  replayed boolean default false
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select action.result_snapshot || jsonb_build_object(
    'export', (action.result_snapshot -> 'export')
      || jsonb_build_object('replayed', $2)
  )
  from public.audit_export_actions action
  where action.id = $1
$$;

create or replace function public.admin_export_audit_logs(
  result_filter text,
  target_type_filter text,
  action_filter text,
  actor_filter text,
  request_id_filter text,
  created_from timestamptz,
  created_to timestamptz,
  export_limit integer,
  reason_code text,
  idempotency_key uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_role public.role_code;
  normalized_result text := lower(btrim(coalesce(result_filter, 'all')));
  normalized_target text := lower(btrim(coalesce(target_type_filter, 'all')));
  normalized_action text := lower(btrim(coalesce(action_filter, '')));
  normalized_actor text := lower(btrim(coalesce(actor_filter, 'all')));
  normalized_request text := btrim(coalesce(request_id_filter, ''));
  normalized_reason text := lower(btrim(coalesce(reason_code, '')));
  normalized_actor_id uuid;
  request_key uuid := idempotency_key;
  request_hash char(64);
  existing_action public.audit_export_actions%rowtype;
  export_id uuid := gen_random_uuid();
  audit_id uuid := gen_random_uuid();
  exported_at timestamptz := clock_timestamp();
  item_rows jsonb;
  candidate_count integer;
  result_snapshot jsonb;
begin
  actor_id := public.admin_require_user_governance_actor();
  if normalized_result not in ('all', 'success', 'failure')
     or (normalized_target <> 'all' and normalized_target !~ '^[a-z0-9_]{1,64}$')
     or (normalized_action <> '' and normalized_action !~ '^[a-z0-9][a-z0-9._-]{0,99}$')
     or (normalized_actor <> 'all' and normalized_actor !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
     or (normalized_request <> '' and normalized_request !~ '^[A-Za-z0-9:_-]{1,180}$') then
    return public.communications_error('AUDIT_FILTER_INVALID', 'Choose supported audit filters.');
  end if;
  if created_from is null or created_to is null or created_from > created_to
     or created_to - created_from > interval '366 days'
     or created_to > clock_timestamp() + interval '5 minutes' then
    return public.communications_error('AUDIT_DATE_RANGE_INVALID', 'Choose a date range of at most 366 days.');
  end if;
  if export_limit is null or export_limit not between 1 and 1000 then
    return public.communications_error('AUDIT_EXPORT_LIMIT_INVALID', 'Use an export limit from 1 to 1000.');
  end if;
  if normalized_reason not in (
    'operational_review', 'security_investigation', 'compliance_request'
  ) then
    return public.communications_error('AUDIT_EXPORT_REASON_INVALID', 'Choose an approved export reason.');
  end if;
  if request_key is null then
    return public.communications_error('AUDIT_EXPORT_IDEMPOTENCY_REQUIRED', 'A UUID idempotency key is required.');
  end if;
  if normalized_actor <> 'all' then
    normalized_actor_id := normalized_actor::uuid;
  end if;

  request_hash := encode(extensions.digest(convert_to(jsonb_build_object(
    'actor_id', actor_id, 'result', normalized_result,
    'target_type', normalized_target, 'action', normalized_action,
    'event_actor', normalized_actor, 'request_id', normalized_request,
    'created_from', created_from, 'created_to', created_to,
    'export_limit', export_limit, 'reason_code', normalized_reason
  )::text, 'UTF8'), 'sha256'), 'hex');
  perform pg_advisory_xact_lock(
    hashtextextended('mt-audit-export-key:' || request_key::text, 0)
  );
  select * into existing_action from public.audit_export_actions action
  where action.idempotency_key = request_key;
  if existing_action.id is not null then
    if existing_action.actor_user_id = actor_id
       and existing_action.request_fingerprint = request_hash then
      return public.admin_audit_export_result(existing_action.id, true);
    end if;
    return public.communications_error(
      'AUDIT_EXPORT_IDEMPOTENCY_CONFLICT',
      'This idempotency key is already bound to another export.'
    );
  end if;

  select role_row.role into actor_role from public.user_roles role_row
  where role_row.user_id = actor_id
  order by case role_row.role
    when 'super_admin'::public.role_code then 1
    when 'admin'::public.role_code then 2
    when 'reviewer'::public.role_code then 3 else 4 end
  limit 1;

  with candidates as (
    select audit.id, audit.created_at,
           row_number() over (order by audit.created_at desc, audit.id desc) as row_number
    from public.audit_logs audit
    where audit.created_at between created_from and created_to
      and (normalized_result = 'all' or audit.result = normalized_result)
      and (normalized_target = 'all' or audit.target_type = normalized_target)
      and (normalized_action = '' or position(normalized_action in lower(audit.action)) = 1)
      and (normalized_actor_id is null or audit.actor_user_id = normalized_actor_id)
      and (normalized_request = '' or position(normalized_request in audit.request_id) = 1)
    order by audit.created_at desc, audit.id desc
    limit export_limit + 1
  )
  select coalesce(jsonb_agg(
      public.admin_audit_summary_json(candidate.id) order by candidate.row_number
    ) filter (where candidate.row_number <= export_limit), '[]'::jsonb),
    count(*)::integer
  into item_rows, candidate_count from candidates candidate;

  result_snapshot := jsonb_build_object(
    'actor', public.admin_audit_actor_json(actor_id),
    'export', jsonb_build_object(
      'id', export_id, 'reason_code', normalized_reason,
      'created_at', exported_at, 'replayed', false
    ),
    'items', item_rows,
    'count', least(candidate_count, export_limit),
    'truncated', candidate_count > export_limit
  );

  insert into public.audit_logs (
    id, actor_user_id, actor_role, action, target_type, target_id,
    request_id, reason_code, before_state, after_state,
    policy_version, result, created_at
  ) values (
    audit_id, actor_id, actor_role, 'audit.exported', 'audit_export',
    export_id::text, request_key::text, normalized_reason, null,
    jsonb_build_object(
      'action', 'export', 'reason_code', normalized_reason,
      'provider_action_required', false
    ), 'mt-audit-export-2026-07-v1', 'success', exported_at
  );
  insert into public.audit_export_actions (
    id, actor_user_id, actor_role, reason_code, filters, export_limit,
    request_fingerprint, idempotency_key, result_snapshot,
    audit_event_id, created_at
  ) values (
    export_id, actor_id, actor_role, normalized_reason,
    jsonb_build_object(
      'result', normalized_result, 'target_type', normalized_target,
      'action', normalized_action, 'actor', normalized_actor,
      'request_id', normalized_request,
      'created_from', created_from, 'created_to', created_to
    ), export_limit, request_hash, request_key, result_snapshot,
    audit_id, exported_at
  );
  return public.admin_audit_export_result(export_id, false);
end;
$$;

revoke all on function public.protect_conversation_identity()
  from public, anon, authenticated, service_role;
revoke all on function public.protect_conversation_participant()
  from public, anon, authenticated, service_role;
revoke all on function public.communications_error(text, text)
  from public, anon, authenticated, service_role;
revoke all on function public.communications_require_actor(boolean)
  from public, anon, authenticated, service_role;
revoke all on function public.notification_safe_json(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.get_my_notification_unread_count()
  from public, anon, authenticated, service_role;
revoke all on function public.list_my_notifications(integer, timestamptz, uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.mark_my_notification_read(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.mark_all_my_notifications_read()
  from public, anon, authenticated, service_role;
revoke all on function public.conversation_work_items(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.conversation_message_json(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.conversation_summary_json(uuid, uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.project_inquiry_result(uuid, boolean)
  from public, anon, authenticated, service_role;
revoke all on function public.create_project_inquiry(
  text, text, text, text, text, text, text, text, text, uuid[], uuid
) from public, anon, authenticated, service_role;
revoke all on function public.list_my_conversations(
  text, integer, timestamptz, uuid
) from public, anon, authenticated, service_role;
revoke all on function public.get_my_conversation(
  uuid, integer, timestamptz, uuid
) from public, anon, authenticated, service_role;
revoke all on function public.conversation_reply_result(uuid, boolean)
  from public, anon, authenticated, service_role;
revoke all on function public.reply_to_conversation(uuid, integer, text, uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.conversation_status_result(uuid, boolean)
  from public, anon, authenticated, service_role;
revoke all on function public.set_my_conversation_status(uuid, integer, text, uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.mark_my_conversation_read(uuid, uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.audit_safe_state(jsonb)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_audit_actor_json(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_audit_summary_json(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_list_audit_logs(
  text, text, text, text, text, timestamptz, timestamptz,
  integer, timestamptz, uuid
) from public, anon, authenticated, service_role;
revoke all on function public.admin_get_audit_log(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_audit_export_result(uuid, boolean)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_export_audit_logs(
  text, text, text, text, text, timestamptz, timestamptz,
  integer, text, uuid
) from public, anon, authenticated, service_role;

grant execute on function public.create_project_inquiry(
  text, text, text, text, text, text, text, text, text, uuid[], uuid
) to anon, authenticated;

grant execute on function public.get_my_notification_unread_count()
  to authenticated;
grant execute on function public.list_my_notifications(integer, timestamptz, uuid)
  to authenticated;
grant execute on function public.mark_my_notification_read(uuid)
  to authenticated;
grant execute on function public.mark_all_my_notifications_read()
  to authenticated;

grant execute on function public.list_my_conversations(
  text, integer, timestamptz, uuid
) to authenticated;
grant execute on function public.get_my_conversation(
  uuid, integer, timestamptz, uuid
) to authenticated;
grant execute on function public.reply_to_conversation(uuid, integer, text, uuid)
  to authenticated;
grant execute on function public.set_my_conversation_status(uuid, integer, text, uuid)
  to authenticated;
grant execute on function public.mark_my_conversation_read(uuid, uuid)
  to authenticated;

grant execute on function public.admin_list_audit_logs(
  text, text, text, text, text, timestamptz, timestamptz,
  integer, timestamptz, uuid
) to authenticated;
grant execute on function public.admin_get_audit_log(uuid)
  to authenticated;
grant execute on function public.admin_export_audit_logs(
  text, text, text, text, text, timestamptz, timestamptz,
  integer, text, uuid
) to authenticated;

commit;

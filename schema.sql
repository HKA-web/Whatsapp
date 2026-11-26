-- =============================================================================
-- DDL SCHEMA WHATSAPP (PostgreSQL)
-- Database yang ditunjuk oleh konfigurasi DATABASES.WHATSAPP di microservice.yaml
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS "whatsapp";

-- -----------------------------------------------------------------------------
-- 1. Table: session
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "whatsapp"."session" (
    "created" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "modified" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "is_removed" BOOLEAN NOT NULL DEFAULT FALSE,
    "read_only" BOOLEAN NOT NULL DEFAULT FALSE,
    "enable" BOOLEAN NOT NULL DEFAULT TRUE,
    "properties" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "description" TEXT NULL,
    "session_id" VARCHAR(25) NOT NULL,
    "session_name" VARCHAR(255) NOT NULL,
    "data" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "status" VARCHAR(100) NOT NULL DEFAULT 'STOPPED',
    "premised" BOOLEAN NOT NULL DEFAULT FALSE,
    "server" VARCHAR(255) NULL,
    CONSTRAINT "session_pkey" PRIMARY KEY ("session_id")
);

-- -----------------------------------------------------------------------------
-- 2. Table: template
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "whatsapp"."template" (
    "created" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "modified" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "is_removed" BOOLEAN NOT NULL DEFAULT FALSE,
    "read_only" BOOLEAN NOT NULL DEFAULT FALSE,
    "enable" BOOLEAN NOT NULL DEFAULT TRUE,
    "properties" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "description" TEXT NULL,
    "template_id" VARCHAR(100) NOT NULL,
    "template_name" VARCHAR(255) NOT NULL,
    "template" TEXT NOT NULL,
    "status" VARCHAR(100) NOT NULL DEFAULT 'ACTIVE',
    "session_id" VARCHAR(25) NULL,
    CONSTRAINT "template_pkey" PRIMARY KEY ("template_id"),
    CONSTRAINT "template_template_session_id_c9403ca1_uniq" UNIQUE ("template", "session_id"),
    CONSTRAINT "template_session_id_f41b1804_fk_session_session_id" 
        FOREIGN KEY ("session_id") REFERENCES "whatsapp"."session"("session_id") DEFERRABLE INITIALLY DEFERRED
);

-- -----------------------------------------------------------------------------
-- 3. Table: command
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "whatsapp"."command" (
    "created" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "modified" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "is_removed" BOOLEAN NOT NULL DEFAULT FALSE,
    "read_only" BOOLEAN NOT NULL DEFAULT FALSE,
    "enable" BOOLEAN NOT NULL DEFAULT TRUE,
    "properties" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "description" TEXT NULL,
    "command_id" VARCHAR(255) NOT NULL,
    "command_name" VARCHAR(255) NOT NULL,
    "command" VARCHAR(255) NOT NULL,
    "command_type" VARCHAR(50) NOT NULL DEFAULT 'TEXT',
    "process" TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    "required_parameter" VARCHAR(255)[] NULL,
    "check_parameter" BOOLEAN NOT NULL DEFAULT FALSE,
    "required_permission" BIGINT[] NULL,
    "check_permission" BOOLEAN NOT NULL DEFAULT FALSE,
    "is_finish" BOOLEAN NOT NULL DEFAULT TRUE,
    "status" VARCHAR(100) NOT NULL DEFAULT 'ACTIVE',
    "mirror_id" VARCHAR(255) NULL,
    "session_id" VARCHAR(25) NULL,
    CONSTRAINT "command_pkey" PRIMARY KEY ("command_id"),
    CONSTRAINT "command_command_session_id_d74acc50_uniq" UNIQUE ("command", "session_id"),
    CONSTRAINT "command_mirror_id_91efbbe1_fk_command_command_id" 
        FOREIGN KEY ("mirror_id") REFERENCES "whatsapp"."command"("command_id") DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT "command_session_id_e2cdb3a8_fk_session_session_id" 
        FOREIGN KEY ("session_id") REFERENCES "whatsapp"."session"("session_id") DEFERRABLE INITIALLY DEFERRED
);

-- -----------------------------------------------------------------------------
-- 4. Table: command_active
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "whatsapp"."command_active" (
    "created" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "modified" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "is_removed" BOOLEAN NOT NULL DEFAULT FALSE,
    "read_only" BOOLEAN NOT NULL DEFAULT FALSE,
    "enable" BOOLEAN NOT NULL DEFAULT TRUE,
    "properties" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "description" TEXT NULL,
    "id" VARCHAR(25) NOT NULL,
    "parameter" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "command_by" VARCHAR(50) NOT NULL,
    "command_date" TIMESTAMPTZ NULL DEFAULT NOW(),
    "command_id" VARCHAR(255) NOT NULL,
    "previous_command_id" VARCHAR(255) NULL,
    CONSTRAINT "command_active_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "command_active_command_id_command_by_77c2a9f8_uniq" UNIQUE ("command_id", "command_by"),
    CONSTRAINT "command_active_command_id_0e498e55_fk_command_command_id" 
        FOREIGN KEY ("command_id") REFERENCES "whatsapp"."command"("command_id") DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT "command_active_previous_command_id_a76d6402_fk_command_c" 
        FOREIGN KEY ("previous_command_id") REFERENCES "whatsapp"."command"("command_id") DEFERRABLE INITIALLY DEFERRED
);

-- -----------------------------------------------------------------------------
-- 5. Table: inbox
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "whatsapp"."inbox" (
    "created" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "modified" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "is_removed" BOOLEAN NOT NULL DEFAULT FALSE,
    "read_only" BOOLEAN NOT NULL DEFAULT FALSE,
    "enable" BOOLEAN NOT NULL DEFAULT TRUE,
    "properties" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "description" TEXT NULL,
    "inbox_id" VARCHAR(100) NOT NULL,
    "message" TEXT NULL,
    "message_type" VARCHAR(50) NOT NULL DEFAULT 'text',
    "inbox_by" VARCHAR(100) NOT NULL,
    "inbox_date" TIMESTAMPTZ NULL DEFAULT NOW(),
    "is_processed" BOOLEAN NOT NULL DEFAULT FALSE,
    "data" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "status" VARCHAR(100) NOT NULL DEFAULT 'RECEIVED',
    "session_id" VARCHAR(25) NULL,
    CONSTRAINT "inbox_pkey" PRIMARY KEY ("inbox_id"),
    CONSTRAINT "inbox_session_id_dac84edb_fk_session_session_id" 
        FOREIGN KEY ("session_id") REFERENCES "whatsapp"."session"("session_id") DEFERRABLE INITIALLY DEFERRED
);

-- -----------------------------------------------------------------------------
-- 6. Table: outbox
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "whatsapp"."outbox" (
    "created" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "modified" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "is_removed" BOOLEAN NOT NULL DEFAULT FALSE,
    "read_only" BOOLEAN NOT NULL DEFAULT FALSE,
    "enable" BOOLEAN NOT NULL DEFAULT TRUE,
    "properties" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "description" TEXT NULL,
    "outbox_id" VARCHAR(100) NOT NULL,
    "sent_id" VARCHAR(100) NOT NULL,
    "message" TEXT NULL,
    "message_type" VARCHAR(50) NOT NULL DEFAULT 'text',
    "outbox_for" VARCHAR(100) NOT NULL,
    "prepare_date" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "retry" INTEGER NOT NULL DEFAULT 0,
    "scheduled" BOOLEAN NOT NULL DEFAULT FALSE,
    "scheduled_date" TIMESTAMPTZ NULL,
    "is_interactive" BOOLEAN NOT NULL DEFAULT FALSE,
    "is_answered" BOOLEAN NOT NULL DEFAULT FALSE,
    "answered_date" TIMESTAMPTZ NULL,
    "data" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "status" VARCHAR(100) NOT NULL DEFAULT 'QUEUED',
    "session_id" VARCHAR(25) NULL,
    "template_id" VARCHAR(100) NULL,
    CONSTRAINT "outbox_pkey" PRIMARY KEY ("outbox_id"),
    CONSTRAINT "outbox_session_id_57a00989_fk_session_session_id" 
        FOREIGN KEY ("session_id") REFERENCES "whatsapp"."session"("session_id") DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT "outbox_template_id_c5914d7e_fk_template_template_id" 
        FOREIGN KEY ("template_id") REFERENCES "whatsapp"."template"("template_id") DEFERRABLE INITIALLY DEFERRED
);

-- -----------------------------------------------------------------------------
-- 7. Table: sent
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "whatsapp"."sent" (
    "created" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "modified" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "is_removed" BOOLEAN NOT NULL DEFAULT FALSE,
    "read_only" BOOLEAN NOT NULL DEFAULT FALSE,
    "enable" BOOLEAN NOT NULL DEFAULT TRUE,
    "properties" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "description" TEXT NULL,
    "sent_id" VARCHAR(100) NOT NULL,
    "message" TEXT NULL,
    "message_type" VARCHAR(50) NOT NULL DEFAULT 'text',
    "sent_for" VARCHAR(100) NOT NULL,
    "sent_date" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "prepare_date" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "retry" INTEGER NOT NULL DEFAULT 0,
    "scheduled" BOOLEAN NOT NULL DEFAULT FALSE,
    "scheduled_date" TIMESTAMPTZ NULL,
    "is_interactive" BOOLEAN NOT NULL DEFAULT FALSE,
    "is_answered" BOOLEAN NOT NULL DEFAULT FALSE,
    "answered_date" TIMESTAMPTZ NULL,
    "data" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "status" VARCHAR(100) NOT NULL DEFAULT 'SENT',
    "session_id" VARCHAR(25) NULL,
    "template_id" VARCHAR(100) NULL,
    CONSTRAINT "sent_pkey" PRIMARY KEY ("sent_id"),
    CONSTRAINT "sent_session_id_7560a0b1_fk_session_session_id" 
        FOREIGN KEY ("session_id") REFERENCES "whatsapp"."session"("session_id") DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT "sent_template_id_0211a79e_fk_template_template_id" 
        FOREIGN KEY ("template_id") REFERENCES "whatsapp"."template"("template_id") DEFERRABLE INITIALLY DEFERRED
);

-- -----------------------------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS "inbox_session_id_dac84edb" ON "whatsapp"."inbox" ("session_id");
CREATE INDEX IF NOT EXISTS "outbox_session_id_57a00989" ON "whatsapp"."outbox" ("session_id");
CREATE INDEX IF NOT EXISTS "outbox_template_id_c5914d7e" ON "whatsapp"."outbox" ("template_id");
CREATE INDEX IF NOT EXISTS "sent_session_id_7560a0b1" ON "whatsapp"."sent" ("session_id");
CREATE INDEX IF NOT EXISTS "sent_template_id_0211a79e" ON "whatsapp"."sent" ("template_id");
CREATE INDEX IF NOT EXISTS "command_session_id_e2cdb3a8" ON "whatsapp"."command" ("session_id");
CREATE INDEX IF NOT EXISTS "command_mirror_id_91efbbe1" ON "whatsapp"."command" ("mirror_id");
CREATE INDEX IF NOT EXISTS "command_active_command_id_0e498e55" ON "whatsapp"."command_active" ("command_id");
CREATE INDEX IF NOT EXISTS "command_active_previous_command_id_a76d6402" ON "whatsapp"."command_active" ("previous_command_id");
CREATE INDEX IF NOT EXISTS "template_session_id_f41b1804" ON "whatsapp"."template" ("session_id");

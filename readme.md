### Setup WhatsApp Engine (`baileys` & `whatsmeow`)

#### A. Engine Baileys (Node.js - Default)
Masuk ke direktori engine Baileys dan install paket dependencies:
```bash
cd whatsapp/engine/baileys
npm install
npm run build
cd ../../..
```

#### B. Engine Whatsmeow (Go - Alternatif)
Pastikan Go portable tersedia di `bin/go/` (atau terpasang di PATH), lalu kompilasi binary:
```bash
cd whatsapp/engine/whatsmeow
../../../bin/go/bin/go.exe build -o whatsmeow.exe ./cmd/server
cd ../../..
```

---

## Cara Menjalankan Layanan

Jalankan **layanan berikut pada terminal terpisah**:

### 1. Jalankan Worker Antrean Huey (Inbox & Outbox)
```bash
python manage.py runhuey --queue whatsapp
```

> [!IMPORTANT]
> **Peran Krusial Worker Huey:**
> 1. **Antrean & Rate Limiting:** Mengantre pesan masuk (`Inbox`) dan keluar (`Outbox`) agar server tidak overload saat ratusan chat masuk serentak, serta melindungi nomor WhatsApp dari risiko pemblokiran (*banned/spam*) akibat pengiriman pesan terlalu cepat.
> 2. **Cronjob Otomatis:** Menjalankan pengecekan otomatis setiap 1 menit (`@huey.db_periodic_task`) untuk pesan broadcast terjadwal (`scheduled = True`) dan pengiriman ulang pesan gagal (*retry*).

### 2. Jalankan WhatsApp Engine
```bash
# Menjalankan Baileys (Default)
python manage.py runwhatsapp

# Atau menjalankan Whatsmeow
python manage.py runwhatsapp --engine=whatsmeow
```

---

## Dokumentasi & Akses API

- **Django Base URL:** `http://localhost:8008`
- **WhatsApp Swagger UI:** `http://localhost:3002/docs`
- **Raw OpenAPI Spec:** `http://localhost:3002/openapi.json`
- **WhatsApp Management REST API:** `http://localhost:8008/whatsapp/api/`

---

## Database DDL (Schema WhatsApp)

Berikut adalah query DDL PostgreSQL lengkap untuk skema dan tabel-tabel modul WhatsApp:

```sql
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
-- 8. Table: datasource (Schema Core - Koneksi Database Dinamis)
-- -----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS "core";
CREATE SCHEMA IF NOT EXISTS "history";

CREATE TABLE IF NOT EXISTS "core"."datasource" (
    "created" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "modified" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "is_removed" BOOLEAN NOT NULL DEFAULT FALSE,
    "read_only" BOOLEAN NOT NULL DEFAULT FALSE,
    "enable" BOOLEAN NOT NULL DEFAULT TRUE,
    "properties" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "description" TEXT NULL,
    "datasource_id" VARCHAR(25) NOT NULL,
    "datasource_name" VARCHAR(255) NOT NULL,
    "engine" VARCHAR(255) NULL,
    "database" VARCHAR(255) NOT NULL,
    "user" VARCHAR(255) NULL,
    "password" BYTEA NULL,
    "host" VARCHAR(255) NULL,
    "port" INTEGER NULL,
    "url" TEXT NULL,
    "status" VARCHAR(100) NOT NULL DEFAULT 'draft',
    CONSTRAINT "datasource_pkey" PRIMARY KEY ("datasource_id"),
    CONSTRAINT "datasource_datasource_name_uniq" UNIQUE ("datasource_name")
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
```

## Dummy Data SQL (Data Contoh)

```sql

-- 1. Dummy Session (Sesi WhatsApp Bot)
INSERT INTO "whatsapp"."session" (
    "created", "modified", "is_removed", "read_only", "enable", "properties",
    "session_id", "session_name", "status", "premised", "server", "data"
) VALUES (
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'default', 'Bot Utama WhatsApp', 'START', FALSE, '127.0.0.1', '{}'::jsonb
) ON CONFLICT ("session_id") DO UPDATE 
SET "session_name" = EXCLUDED."session_name", "status" = EXCLUDED."status";

-- 2. Dummy Template (Pesan Template Notifikasi/Balasan)
INSERT INTO "whatsapp"."template" (
    "created", "modified", "is_removed", "read_only", "enable", "properties",
    "template_id", "template_name", "template", "status", "session_id"
) VALUES 
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'TPL_WELCOME', 'Template Sambutan', 
    'Halo {{nama}}, terima kasih telah menghubungi layanan kami. Ketik *menu* untuk melihat opsi.', 
    'ACTIVE', 'default'
),
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'TPL_NOTIFIKASI', 'Template Notifikasi Transaksi', 
    'Pemberitahuan: Transaksi dengan ID {{transaksi_id}} berhasil diproses.', 
    'ACTIVE', 'default'
)
ON CONFLICT ("template_id") DO NOTHING;

-- 3. Dummy Command: Single-Turn (Perintah Langsung Selesai)
-- Perintah Single-Turn memiliki flag "is_finish" = TRUE, artinya bot langsung merespon
-- dan langsung menyelesaikan tugasnya tanpa menunggu percakapan bertingkat / multi-turn.

-- 3.1. Single Command: Tipe TXT (Pesan Teks Sederhana)
INSERT INTO "whatsapp"."command" (
    "created", "modified", "is_removed", "read_only", "enable", "properties",
    "command_id", "command_name", "command", "command_type", "process", 
    "check_parameter", "check_permission", "is_finish", "status", "session_id"
) VALUES 
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_HALO', 'Command Halo', 'halo', 'txt', 
    ARRAY['Halo! Selamat datang di Layanan Pelanggan. Ada yang bisa kami bantu? Ketik *menu* untuk informasi lebih lanjut.'], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'default'
),
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_BANTUAN', 'Command Bantuan', 'bantuan', 'txt', 
    ARRAY['Berikut adalah perintah yang dapat Anda gunakan:' || E'\n' || '- *menu* : Melihat daftar layanan interaktif' || E'\n' || '- *halo* : Sapaan bot' || E'\n' || '- *info* : Memeriksa performa server bot' || E'\n' || '- *ping* : Mengecek status bot' || E'\n' || '- *rvo* / *buka* : Membuka media sekali lihat (reply pesan view-once)'], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'default'
)
ON CONFLICT ("command_id") DO UPDATE 
SET "command" = EXCLUDED."command", "process" = EXCLUDED."process";

-- 3.2. Single Command: Tipe PY (Action Nyata: Buka Pesan Sekali Lihat / Read View Once & Alias Mirror)
-- Menjalankan script Python yang memanggil '_handle_rvo_command(inbox)'.
-- Saat user me-reply foto/video sekali lihat dengan teks 'rvo', 'buka', atau 'lihat',
-- bot mendownload media via Baileys API dan mengirimkannya sebagai media reguler ke Outbox.
INSERT INTO "whatsapp"."command" (
    "created", "modified", "is_removed", "read_only", "enable", "properties",
    "command_id", "command_name", "command", "command_type", "process", 
    "check_parameter", "check_permission", "is_finish", "status", "mirror_id", "session_id"
) VALUES 
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_RVO', 'Buka Pesan Sekali Lihat (View Once)', 'rvo', 'py', 
    ARRAY['from whatsapp.tasks.inbox import _handle_rvo_command' || E'\n' || '_handle_rvo_command(inbox)'], 
    FALSE, FALSE, TRUE, 'ACTIVE', NULL, NULL
)
ON CONFLICT ("command_id") DO UPDATE 
SET "command" = EXCLUDED."command", "process" = EXCLUDED."process", "is_finish" = EXCLUDED."is_finish", "status" = EXCLUDED."status";

-- Alias / Mirror untuk Command RVO ('buka' dan 'lihat' menginduk ke 'CMD_RVO')
INSERT INTO "whatsapp"."command" (
    "created", "modified", "is_removed", "read_only", "enable", "properties",
    "command_id", "command_name", "command", "command_type", "process", 
    "check_parameter", "check_permission", "is_finish", "status", "mirror_id", "session_id"
) VALUES 
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_RVO_BUKA', 'Alias: Buka Pesan', 'buka', 'py', 
    '{}'::text[], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'CMD_RVO', NULL
),
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_RVO_LIHAT', 'Alias: Lihat Pesan', 'lihat', 'py', 
    '{}'::text[], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'CMD_RVO', NULL
)
ON CONFLICT ("command_id") DO UPDATE 
SET "command" = EXCLUDED."command", "mirror_id" = EXCLUDED."mirror_id", "is_finish" = EXCLUDED."is_finish", "status" = EXCLUDED."status";

-- 4. Dummy Command: Multi-Turn / Percakapan Berkelanjutan (CommandActive)
-- User mengetik 'menu' -> Bot menyimpan CommandActive -> User membalas angka '1', '2', atau '3'
INSERT INTO "whatsapp"."command" (
    "created", "modified", "is_removed", "read_only", "enable", "properties",
    "command_id", "command_name", "command", "command_type", "process", 
    "check_parameter", "check_permission", "is_finish", "status", "session_id"
) VALUES 
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_MENU_UTAMA', 'Menu Utama Layanan', 'menu', 'txt', 
    ARRAY['Silakan pilih menu layanan kami:' || E'\n' || '1. Layanan Informasi Akun' || E'\n' || '2. Cek Status Pesanan' || E'\n' || '3. Hubungi Customer Service' || E'\n\n' || 'Ketik angka *1*, *2*, atau *3* untuk melanjutkan.'], 
    FALSE, FALSE, FALSE, 'ACTIVE', 'default'
),
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_MENU_1', 'Menu 1: Informasi Akun', 'menu/1', 'txt', 
    ARRAY['ðŸ“Œ *Layanan Informasi Akun*' || E'\n' || 'Untuk mengakses akun Anda, silakan kunjungi portal kami di https://example.com/akun'], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'default'
),
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_MENU_2', 'Menu 2: Status Pesanan', 'menu/2', 'txt', 
    ARRAY['ðŸ“¦ *Status Pesanan*' || E'\n' || 'Pesanan Anda saat ini sedang dikemas oleh tim gudang. Terima kasih atas kesabaran Anda!'], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'default'
),
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_MENU_3', 'Menu 3: Customer Service', 'menu/3', 'txt', 
    ARRAY['ðŸ‘¨â€ðŸ’¼ *Customer Service*' || E'\n' || 'Mohon tunggu sejenak, petugas kami akan segera membalas pesan Anda.'], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'default'
)
ON CONFLICT ("command_id") DO UPDATE 
SET "command" = EXCLUDED."command", "process" = EXCLUDED."process", "is_finish" = EXCLUDED."is_finish";

-- 5. Dummy Outbox (Contoh Antrean Pesan Keluar)
INSERT INTO "whatsapp"."outbox" (
    "created", "modified", "is_removed", "read_only", "enable", "properties",
    "outbox_id", "sent_id", "message", "message_type", "outbox_for", "prepare_date", "retry", "scheduled", 
    "is_interactive", "is_answered", "data", "status", "session_id"
) VALUES (
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'OUTBOX_DUMMY_001', 'SENT_DUMMY_001', 
    'Halo! Ini adalah contoh pesan outbox WhatsApp.', 
    'conversation', '6281234567890', NOW(), 0, FALSE, FALSE, FALSE, 
    '{}'::jsonb, 'QUEUED', 'default'
)
ON CONFLICT ("outbox_id") DO NOTHING;

-- 6. Dummy Datasource (Koneksi Database Eksternal Dinamis)
-- Tabel ini berada di schema "core"."datasource" (pada database utama atau database WHATSAPP).
-- Digunakan oleh action command WhatsApp (misal: Approval HRMS) untuk terhubung secara runtime ke database eksternal (PostgreSQL, MySQL, dsb).
INSERT INTO "core"."datasource" (
    "created", "modified", "is_removed", "read_only", "enable", "properties",
    "description", "datasource_id", "datasource_name", "engine", "database",
    "user", "password", "host", "port", "url", "status"
) VALUES 
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'Database HRMS NJRM', 'HRMS.NJRM', 'HRMS.NJRM', 
    'django.db.backends.postgresql', 'HRMS.NJRM', 'postgres', 
    '\x1cfe9601f12f195729d819525de3970c290c1e4592cf0488a1d0b4efd38c347a8c3e9da73f53863a'::bytea, 
    '192.168.6.25', 17296, NULL, 'draft'
)
ON CONFLICT ("datasource_id") DO UPDATE 
SET "datasource_name" = EXCLUDED."datasource_name",
    "engine" = EXCLUDED."engine",
    "database" = EXCLUDED."database",
    "user" = EXCLUDED."user",
    "password" = EXCLUDED."password",
    "host" = EXCLUDED."host",
    "port" = EXCLUDED."port",
    "url" = EXCLUDED."url";

-- 7. Dummy Command: Tipe PY (Koneksi ke Datasource & Kirim Balasan via Outbox)
-- Perintah ini mengeksekusi kode Python secara dinamis saat user mengirim pesan 'testds'.
-- Mengambil konfigurasi database dari Datasource 'HRMS.TRIAL', menjalankan query SELECT 1, lalu mengirim hasil ke WhatsApp user.
INSERT INTO "whatsapp"."command" (
    "created", "modified", "is_removed", "read_only", "enable", "properties",
    "command_id", "command_name", "command", "command_type", "process", 
    "check_parameter", "check_permission", "is_finish", "status", "session_id"
) VALUES 
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_TEST_DS', 'Test Koneksi Datasource HRMS.TRIAL', 'testds', 'py', 
    ARRAY['import logging
from core.models import Datasource
from core.utils import database
from whatsapp.models import Outbox

logger = logging.getLogger(__name__)

try:
    ds = Datasource.objects.get(datasource_id=''HRMS.TRIAL'')
    res = database.fetchone(ds.connection(), ''SELECT 1 as test, current_database() as db, now() as db_time'')
    reply = (
        ''âœ… *Koneksi Datasource Berhasil!*\n\n''
        f''â€¢ ID: *{ds.datasource_id}*\n''
        f''â€¢ Host: `{ds.host}:{ds.port}`\n''
        f''â€¢ Database: *{res.db}*\n''
        f''â€¢ Query Result (SELECT 1): `{res.test}`\n''
        f''â€¢ DB Timestamp: `{res.db_time}`''
    )
except Exception as e:
    logger.error(f''Error datasource: {e}'', exc_info=True)
    reply = f''âŒ *Koneksi Datasource Gagal:*\n{e}''

Outbox.objects.using(''WHATSAPP'').create(
    message=reply,
    message_type=''conversation'',
    outbox_for=inbox.inbox_by,
    session_id=inbox.session_id,
    properties=dict(command=command_active.command.pk, inbox=inbox.inbox_id),
    data=dict(reply_to=inbox.inbox_id, quoted=inbox.data),
)'], 
    FALSE, FALSE, TRUE, 'ACTIVE', NULL
)
ON CONFLICT ("command_id") DO UPDATE 
SET "command" = EXCLUDED."command", "process" = EXCLUDED."process", "command_type" = EXCLUDED."command_type";
```

> [!TIP]
> **Input Datasource via Django ORM atau REST API:**
> Selain SQL langsung, pembuatan `Datasource` juga dapat dilakukan melalui Python Django ORM atau REST API (`/core/api/datasource/`). Keuntungannya, password teks biasa (`plain text`) akan dienkripsi secara otomatis menggunakan AES-GCM (`EncryptedCharField`):
> ```bash
> python manage.py shell -c "from core.models import Datasource; Datasource.objects.update_or_create(datasource_id='HRMS.TRIAL', defaults=dict(datasource_name='HRMS.TRIAL', engine='django.db.backends.postgresql', database='HRMS.SNI.OKT', user='postgres', password='111111', host='192.168.123.87', port=5432, enable=True))"
> ```

> [!TIP]
> **Pendaftaran Single Command via Django ORM (Python):**
> Pembuatan atau update perintah WhatsApp juga dapat dijalankan langsung via Django Shell:
> ```bash
> python manage.py shell -c "from whatsapp.models import Command; cmd, _ = Command.objects.using('WHATSAPP').update_or_create(command_id='CMD_RVO', defaults=dict(command='rvo', command_name='Buka Pesan Sekali Lihat', command_type=Command.Type.PY, process=['from whatsapp.tasks.inbox import _handle_rvo_command\n_handle_rvo_command(inbox)'], is_finish=True, enable=True, status='published')); Command.objects.using('WHATSAPP').update_or_create(command_id='CMD_RVO_BUKA', defaults=dict(command='buka', command_name='Alias Buka Pesan', command_type=Command.Type.PY, mirror=cmd, is_finish=True, enable=True, status='published'))"
> ```

---

## Panduan Pengujian API WhatsApp (Outbox & Fitur Lengkap)

Semua pengujian pengiriman pesan keluar dapat dilakukan melalui endpoint Django REST API (diproses secara aman melalui antrean Worker Huey):
* **Endpoint:** `POST http://localhost:8008/whatsapp/api/outbox/`
* **Content-Type:** `application/json`

> [!NOTE]
> Semua nomor telepon pada contoh di bawah ini telah disamarkan.
> * Ganti `session_id`: `"6285XXXXXXXXX"` dengan ID sesi bot pengirim Anda.
> * Ganti `outbox_for`: `"6281XXXXXXXXX@s.whatsapp.net"` dengan nomor WhatsApp penerima (mendukung format `6281XXXXXXXXX@s.whatsapp.net`, nomor biasa `6281XXXXXXXXX`, maupun ID grup `...@g.us`).

---

### 1. Kirim Pesan Teks Biasa (`conversation`)
```json
{
  "message": "Halo, ini adalah contoh pesan teks biasa dari bot WhatsApp.",
  "message_type": "conversation",
  "outbox_for": "6281XXXXXXXXX@s.whatsapp.net",
  "session_id": "6285XXXXXXXXX",
  "data": {},
  "properties": {}
}
```

---

### 2. Kirim Gambar (`image`)
Mendukung URL gambar publik (HTTP/HTTPS) atau Base64 Data URI secara langsung:

**A. Menggunakan URL Gambar Publik:**
```json
{
  "message": "Berikut adalah contoh foto pemandangan.",
  "message_type": "image",
  "outbox_for": "6281XXXXXXXXX@s.whatsapp.net",
  "session_id": "6285XXXXXXXXX",
  "data": {
    "url": "https://picsum.photos/500/300.jpg"
  },
  "properties": {}
}
```

**B. Menggunakan Base64 Data URI (Tanpa Perlu Hosting Luar):**
```json
{
  "message": "Foto dikirim langsung dari string Base64.",
  "message_type": "image",
  "outbox_for": "6281XXXXXXXXX@s.whatsapp.net",
  "session_id": "6285XXXXXXXXX",
  "data": {
    "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg=="
  },
  "properties": {}
}
```

---

### 3. Kirim File / Dokumen (`file` atau `document`)
Mendukung pengiriman file PDF, Excel (`.xlsx`), Word (`.docx`), ZIP, dll:
```json
{
  "message": "Berikut terlampir dokumen laporan bulanan.",
  "message_type": "file",
  "outbox_for": "6281XXXXXXXXX@s.whatsapp.net",
  "session_id": "6285XXXXXXXXX",
  "data": {
    "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
    "filename": "Laporan_Bulanan.pdf"
  },
  "properties": {}
}
```
* **`data.filename`**: Nama file yang akan tampil di aplikasi WhatsApp penerima.
* **`data.url`**: Tautan langsung dokumen yang dapat diunduh.

---

### 4. Kirim Balasan / Quote Pesan Tertentu (`reply_to`)
Mengutip pesan WhatsApp sebelumnya (berfungsi untuk pesan teks, gambar, maupun dokumen):
```json
{
  "message": "Ini adalah jawaban balasan untuk pesan Anda sebelumnya.",
  "message_type": "conversation",
  "outbox_for": "6281XXXXXXXXX@s.whatsapp.net",
  "session_id": "6285XXXXXXXXX",
  "data": {},
  "properties": {
    "reply_to": "3EB0B1E9D3241E949EE339"
  }
}
```
* **`reply_to`**: ID pesan WhatsApp yang ingin dibalas/dikutip.

---

### 5. Simulasi Mengetik Human-Like (`simulateTyping` & `typingDelay`)
Menampilkan status **"sedang mengetik..." (composing)** di WhatsApp penerima selama durasi tertentu sebelum pesan dikirim agar bot terlihat alami:
```json
{
  "message": "Pesan ini dikirim setelah status mengetik selama 2 detik.",
  "message_type": "conversation",
  "outbox_for": "6281XXXXXXXXX@s.whatsapp.net",
  "session_id": "6285XXXXXXXXX",
  "data": {},
  "properties": {
    "simulateTyping": true,
    "typingDelay": 2000
  }
}
```
* **`simulateTyping`**: Set `true` untuk mengaktifkan status typing.
* **`typingDelay`**: Durasi simulasi mengetik dalam milidetik (misal `2000` = 2 detik).

---

### 6. Pesan Terjadwal (`scheduled` & `scheduled_date`)
Pesan akan disimpan di antrean dan dikirim secara otomatis oleh worker Huey saat waktu jadwal tiba:
```json
{
  "message": "Pengingat jadwal pertemuan jam 15.00 WIB.",
  "message_type": "conversation",
  "outbox_for": "6281XXXXXXXXX@s.whatsapp.net",
  "session_id": "6285XXXXXXXXX",
  "scheduled": true,
  "scheduled_date": "2026-11-26T15:00:00+07:00",
  "data": {},
  "properties": {}
}
```
* **`scheduled`**: Set `true`.
* **`scheduled_date`**: Waktu pengiriman dalam format ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ` atau dengan timezone `+07:00`).

---

### 7. Kirim Menggunakan Template Dinamis (`template_id` + `data`)
Menggunakan template Django yang telah didaftarkan di tabel `whatsapp.template`. Teks pesan akan di-render secara otomatis dari parameter objek `data` tanpa perlu menulis teks manual di kolom `message`:
```json
{
  "template_id": "TPL_SLIP_GAJI",
  "message_type": "conversation",
  "outbox_for": "6281XXXXXXXXX@s.whatsapp.net",
  "session_id": "6285XXXXXXXXX",
  "data": {
    "nama": "Budi Santoso",
    "periode": "November 2026",
    "gaji_pokok": "5.000.000",
    "tunjangan": "1.500.000",
    "total": "6.500.000"
  },
  "properties": {}
}
```

---

### 8. Perintah Interaktif Masuk (Incoming Commands via Chat WA)
Selain mengirim pesan keluar (Outbox), bot juga dapat merespon perintah interaktif saat dikirim langsung ke nomor bot atau ke dalam grup:
1. **`ping`**: Menguji apakah bot aktif dan merespon dengan cepat.
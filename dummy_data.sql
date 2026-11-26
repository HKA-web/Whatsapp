-- =============================================================================
-- DUMMY DATA SCHEMA WHATSAPP (PostgreSQL)
-- Database yang ditunjuk oleh konfigurasi DATABASES.WHATSAPP di microservice.yaml
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Dummy Session (Sesi WhatsApp Bot)
-- -----------------------------------------------------------------------------
INSERT INTO "whatsapp"."session" (
    "created", "modified", "is_removed", "read_only", "enable", "properties",
    "session_id", "session_name", "status", "premised", "server", "data"
) VALUES (
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'default', 'Bot Utama WhatsApp', 'START', FALSE, '127.0.0.1', '{}'::jsonb
) ON CONFLICT ("session_id") DO UPDATE 
SET "session_name" = EXCLUDED."session_name", "status" = EXCLUDED."status";

-- -----------------------------------------------------------------------------
-- 2. Dummy Template (Pesan Template Balasan / Notifikasi)
-- -----------------------------------------------------------------------------
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

-- -----------------------------------------------------------------------------
-- 3. Dummy Command: Sapaan & Bantuan (Single-Turn Command)
-- -----------------------------------------------------------------------------
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
    ARRAY['Berikut adalah perintah yang dapat Anda gunakan:' || E'\n' || '- *menu* : Melihat daftar layanan interaktif' || E'\n' || '- *halo* : Sapaan bot' || E'\n' || '- *info* : Memeriksa performa server bot' || E'\n' || '- *ping* : Mengecek status bot'], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'default'
)
ON CONFLICT ("command_id") DO UPDATE 
SET "command" = EXCLUDED."command", "process" = EXCLUDED."process";

-- -----------------------------------------------------------------------------
-- 4. Dummy Command: Multi-Turn / Percakapan Berkelanjutan (CommandActive)
--    User mengetik 'menu' -> Bot menyimpan CommandActive -> User balas '1', '2', atau '3'
-- -----------------------------------------------------------------------------
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
    ARRAY['📌 *Layanan Informasi Akun*' || E'\n' || 'Untuk mengakses akun Anda, silakan kunjungi portal kami di https://example.com/akun'], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'default'
),
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_MENU_2', 'Menu 2: Status Pesanan', 'menu/2', 'txt', 
    ARRAY['📦 *Status Pesanan*' || E'\n' || 'Pesanan Anda saat ini sedang dikemas oleh tim gudang. Terima kasih atas kesabaran Anda!'], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'default'
),
(
    NOW(), NOW(), FALSE, FALSE, TRUE, '{}'::jsonb,
    'CMD_MENU_3', 'Menu 3: Customer Service', 'menu/3', 'txt', 
    ARRAY['👨‍💼 *Customer Service*' || E'\n' || 'Mohon tunggu sejenak, petugas kami akan segera membalas pesan Anda.'], 
    FALSE, FALSE, TRUE, 'ACTIVE', 'default'
)
ON CONFLICT ("command_id") DO UPDATE 
SET "command" = EXCLUDED."command", "process" = EXCLUDED."process", "is_finish" = EXCLUDED."is_finish";

-- -----------------------------------------------------------------------------
-- 5. Dummy Outbox (Contoh Antrean Pesan Keluar)
-- -----------------------------------------------------------------------------
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

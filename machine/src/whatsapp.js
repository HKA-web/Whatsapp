import {
  makeWASocket,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
  Browsers,
  makeCacheableSignalKeyStore,
  proto,
  normalizeMessageContent,
  getContentType,
} from '@whiskeysockets/baileys';
import NodeCache from '@cacheable/node-cache';
import pino from 'pino';
import fs from 'fs';
import path from 'path';
import axios from 'axios';
import WebSocket from 'ws';
import { deleteSessionFolder } from './utils/config.js';

// Cache sederhana untuk retry counter dan message store Baileys (anti "Waiting for this message")
export class SimpleCache {
  constructor(maxSize = 3000) {
    this.map = new Map();
    this.maxSize = maxSize;
  }
  get(key) {
    return this.map.get(key);
  }
  set(key, value) {
    if (this.map.has(key)) {
      this.map.delete(key);
    } else if (this.map.size >= this.maxSize) {
      const firstKey = this.map.keys().next().value;
      if (firstKey !== undefined) {
        this.map.delete(firstKey);
      }
    }
    this.map.set(key, value);
    return this;
  }
  del(key) {
    return this.map.delete(key);
  }
  delete(key) {
    return this.map.delete(key);
  }
  has(key) {
    return this.map.has(key);
  }
  entries() {
    return this.map ? Array.from(this.map.entries()) : [];
  }
  keys() {
    return this.map ? Array.from(this.map.keys()) : [];
  }
  values() {
    return this.map ? Array.from(this.map.values()) : [];
  }
  forEach(callback, thisArg) {
    return this.map.forEach(callback, thisArg);
  }
  clear() {
    return this.map.clear();
  }
  get size() {
    return this.map.size;
  }
  [Symbol.iterator]() {
    return this.map[Symbol.iterator]();
  }
}

import { fileURLToPath } from 'url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Session Folder Root - Simpan di whatsapp/machine/sessions (persistent di luar dist)
const machineRoot = path.resolve(__dirname, '..');
const sessionRoot = path.resolve(machineRoot, 'sessions');
if (!fs.existsSync(sessionRoot)) {
  fs.mkdirSync(sessionRoot, { recursive: true });
}

const messageStore = new SimpleCache(5000);
const retryCache = new NodeCache({ stdTTL: 300, useClones: false });
const messageKeyStore = new SimpleCache(5000);

// Disk persistence untuk message store agar tidak hilang saat restart
const messageStoreFile = path.resolve(sessionRoot, 'message_store.json');
let diskStore = {};
try {
  if (fs.existsSync(messageStoreFile)) {
    diskStore = JSON.parse(fs.readFileSync(messageStoreFile, 'utf-8'));
    console.log(`[Store] Memuat ${Object.keys(diskStore).length} pesan dari cache disk.`);
  }
} catch (e) {
  diskStore = {};
}

// Mapping LID ke Nomor HP asli (@s.whatsapp.net)
const lidMapFile = path.resolve(sessionRoot, 'lid_map.json');
let lidMap = {};
try {
  if (fs.existsSync(lidMapFile)) {
    lidMap = JSON.parse(fs.readFileSync(lidMapFile, 'utf-8'));
  }
} catch (e) {
  lidMap = {};
}

function saveLidMap() {
  try {
    fs.writeFileSync(lidMapFile, JSON.stringify(lidMap, null, 2), 'utf-8');
  } catch (_) {}
}

let saveTimeout = null;
function scheduleSaveDiskStore() {
  if (saveTimeout) return;
  saveTimeout = setTimeout(() => {
    saveTimeout = null;
    try {
      const keys = Object.keys(diskStore);
      if (keys.length > 5000) {
        for (let i = 0; i < keys.length - 5000; i++) {
          delete diskStore[keys[i]];
        }
      }
      fs.writeFileSync(messageStoreFile, JSON.stringify(diskStore), 'utf-8');
    } catch (err) {
      console.error('[Store] Gagal menyimpan message store ke disk:', err.message);
    }
  }, 1000);
}

export function isMatchingId(k, targetId) {
  if (!k || !targetId) return false;
  const strK = String(k).trim();
  const strTarget = String(targetId).trim();
  if (!strK || !strTarget) return false;
  if (strK === strTarget) return true;

  // Match delimiter suffixes (-1, _1, :1, @...)
  if (strK.startsWith(strTarget + '-') || strTarget.startsWith(strK + '-')) return true;
  if (strK.startsWith(strTarget + '_') || strTarget.startsWith(strK + '_')) return true;
  if (strK.startsWith(strTarget + ':') || strTarget.startsWith(strK + ':')) return true;

  // Match clean base IDs if both share the exact base ID and length is sufficient (>= 8)
  const baseK = strK.split(/[-_:@]/)[0];
  const baseTarget = strTarget.split(/[-_:@]/)[0];
  if (baseK && baseTarget && baseK === baseTarget && baseTarget.length >= 8) {
    return true;
  }
  return false;
}

export function saveMessageToStore(id, message, key = null) {
  if (!id || !message) return;
  const strId = String(id).trim();
  if (!strId) return;

  const actualMsg = message.message || message;
  const actualKey = key || message.key || null;

  messageStore.set(strId, actualMsg);
  diskStore[strId] = actualKey ? { key: actualKey, message: actualMsg } : actualMsg;
  if (actualKey) {
    messageKeyStore.set(strId, actualKey);
  }
  // Jika id memiliki suffix "-1" (umum pada group senderKeys), simpan juga versi clean ID
  if (strId.includes('-')) {
    const cleanId = strId.replace(/-\d+$/, '');
    if (cleanId && cleanId !== strId) {
      if (!messageStore.has(cleanId)) messageStore.set(cleanId, actualMsg);
      if (!diskStore[cleanId]) diskStore[cleanId] = diskStore[strId];
      if (actualKey && !messageKeyStore.has(cleanId)) messageKeyStore.set(cleanId, actualKey);
    }
  }
  scheduleSaveDiskStore();
}

export function hasMediaMessageKeys(msg) {
  if (!msg) return false;
  let unwrapped = msg.message || msg;
  for (let i = 0; i < 5; i++) {
    const next =
      unwrapped?.viewOnceMessage?.message ||
      unwrapped?.viewOnceMessageV2?.message ||
      unwrapped?.viewOnceMessageV2Extension?.message ||
      unwrapped?.ephemeralMessage?.message ||
      unwrapped?.documentWithCaptionMessage?.message ||
      unwrapped?.editedMessage?.message;
    if (!next) break;
    unwrapped = next;
  }
  const media =
    unwrapped?.imageMessage ||
    unwrapped?.videoMessage ||
    unwrapped?.audioMessage ||
    unwrapped?.documentMessage ||
    unwrapped?.stickerMessage;
  if (!media) return false;
  const hasUrl = Boolean(media.url || media.directPath);
  const hasKey = Boolean(
    media.mediaKey &&
    (Buffer.isBuffer(media.mediaKey) ||
      (typeof media.mediaKey === 'object' && (media.mediaKey.data || media.mediaKey.type === 'Buffer')) ||
      (Array.isArray(media.mediaKey) && media.mediaKey.length > 0) ||
      (typeof media.mediaKey === 'string' && media.mediaKey.length > 0))
  );
  return hasUrl && hasKey;
}

export function findLatestMediaMessage(chatId, participant = null) {
  if (!chatId) return null;
  const targetChat = toJid(chatId);
  const targetPart = participant ? toJid(participant) : null;

  const checkEntry = (id, rawVal) => {
    const msg = rawVal?.message || rawVal;
    if (!msg || !hasMediaMessageKeys(msg)) return null;
    const key = messageKeyStore.get(id) || rawVal?.key;
    if (key) {
      const msgChat = toJid(key.remoteJid);
      if (msgChat === targetChat) {
        if (!targetPart || !key.participant || toJid(key.participant) === targetPart) {
          return { key, message: msg };
        }
      }
    }
    return null;
  };

  // 1. Cek cache in-memory secara terbalik
  try {
    const entries = typeof messageStore.entries === 'function' ? Array.from(messageStore.entries()) : [];
    for (let i = entries.length - 1; i >= 0; i--) {
      const [id, msg] = entries[i];
      const match = checkEntry(id, msg);
      if (match) return match;
    }
  } catch (e) {
    console.warn('[findLatestMediaMessage] Memory cache check error:', e?.message);
  }

  // 2. Cek diskStore secara terbalik
  try {
    const diskKeys = Object.keys(diskStore || {});
    for (let i = diskKeys.length - 1; i >= 0; i--) {
      const id = diskKeys[i];
      const rawVal = diskStore[id];
      const match = checkEntry(id, rawVal);
      if (match) return match;
    }
  } catch (e) {
    console.warn('[findLatestMediaMessage] DiskStore check error:', e?.message);
  }

  return null;
}

export function getMessageFromStore(id) {
  if (!id) return undefined;
  const strId = String(id).trim();
  if (!strId) return undefined;

  let msg = messageStore.get(strId) || diskStore[strId];
  if (!msg && strId.includes('-')) {
    const cleanId = strId.replace(/-\d+$/, '');
    msg = messageStore.get(cleanId) || diskStore[cleanId];
  }
  if (!msg) {
    msg = messageStore.get(`${strId}-1`) || diskStore[`${strId}-1`];
  }
  if (!msg) {
    for (const [k, v] of messageStore.entries()) {
      if (isMatchingId(k, strId)) {
        msg = v;
        break;
      }
    }
  }
  if (!msg) {
    for (const [k, v] of Object.entries(diskStore)) {
      if (isMatchingId(k, strId)) {
        msg = v;
        break;
      }
    }
  }
  if (msg && !messageStore.has(strId)) {
    messageStore.set(strId, msg);
  }
  return msg || undefined;
}

export function getMessageKeyFromStore(id) {
  if (!id) return undefined;
  const strId = String(id).trim();
  if (!strId) return undefined;

  let storedKey = messageKeyStore.get(strId);
  if (!storedKey && strId.includes('-')) {
    const cleanId = strId.replace(/-\d+$/, '');
    storedKey = messageKeyStore.get(cleanId);
  }
  if (!storedKey) {
    storedKey = messageKeyStore.get(`${strId}-1`);
  }
  if (!storedKey) {
    for (const [k, v] of messageKeyStore.entries()) {
      if (isMatchingId(k, strId)) {
        storedKey = v;
        break;
      }
    }
  }
  return storedKey || undefined;
}

export function getQuotedMessage(id, fallbackJid = null) {
  if (!id) return null;
  const strId = String(id).trim();
  if (!strId) return null;

  const msgContent = getMessageFromStore(strId);
  const storedKey = getMessageKeyFromStore(strId);
  const key = storedKey
    ? {
        ...storedKey,
        remoteJid: toJid(storedKey.remoteJid || fallbackJid),
        participant: storedKey.participant ? toJid(storedKey.participant) : undefined,
      }
    : {
        remoteJid: toJid(fallbackJid),
        fromMe: false,
        id: strId,
      };
  return {
    key,
    message: msgContent || { conversation: '' },
  };
}

// Status Enum ala WAHA
export const SessionStatus = {
  STARTING: 'STARTING',
  SCAN_QR_CODE: 'SCAN_QR_CODE',
  WORKING: 'WORKING',
  FAILED: 'FAILED',
  STOPPED: 'STOPPED',
};

// In-Memory Session Store
const sessions = new Map();

// ==========================================
// Webhook & Django WebSocket Integration
// ==========================================
const webhookHttp = process.env.WEBHOOK_URL || 'http://127.0.0.1:8008/whatsapp/webhook/';
const wsUrl = webhookHttp
  .replace(/^http/, 'ws')
  .replace(/\/whatsapp\/webhook\/?$/, '/ws/whatsapp/webhook/');

let djangoWs = null;
let wsReconnectTimer = null;

function connectDjangoWs() {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }

  try {
    djangoWs = new WebSocket(wsUrl);

    djangoWs.on('open', () => {
      console.log('✅ Connected to Django WebSocket at ' + wsUrl);
    });

    djangoWs.on('error', (err) => {
      // console.error('❌ Django WS Error:', err.message);
    });

    djangoWs.on('close', () => {
      if (!wsReconnectTimer) {
        wsReconnectTimer = setTimeout(connectDjangoWs, 3000);
      }
    });
  } catch (err) {
    if (!wsReconnectTimer) {
      wsReconnectTimer = setTimeout(connectDjangoWs, 3000);
    }
  }
}
connectDjangoWs();

export function sendToDjango(payload) {
  // 1. Kirim via WebSocket jika terhubung
  if (djangoWs && djangoWs.readyState === WebSocket.OPEN) {
    try {
      djangoWs.send(typeof payload === 'string' ? payload : JSON.stringify(payload));
      return true;
    } catch (err) {
      console.error('❌ Gagal kirim ke Django WS:', err.message);
    }
  }

  // 2. Fallback kirim via HTTP POST jika WebSocket offline / belum siap
  if (webhookHttp && !webhookHttp.startsWith('ws:')) {
    axios
      .post(webhookHttp, payload, { timeout: 3000 })
      .then((res) => {
        console.log(`📡 [HTTP WEBHOOK FALLBACK] Berhasil mengirim event '${payload?.event || 'unknown'}' ke ${webhookHttp} (Status: ${res.status})`);
      })
      .catch((err) => {
        console.warn(`⚠️ [HTTP WEBHOOK FALLBACK ERROR] Gagal mengirim ke ${webhookHttp}:`, err?.message || err);
      });
  }
  return false;
}

// ==========================================
// Helper Format JID / Nomor HP
// ==========================================
export function toJid(input) {
  if (!input) return '';
  let str = String(input).trim();

  // Sudah format JID WhatsApp (@s.whatsapp.net, @g.us, @lid)
  if (str.includes('@s.whatsapp.net') || str.includes('@g.us') || str.includes('@lid')) {
    return str;
  }

  // Format grup
  if (str.includes('-') && !str.startsWith('+')) {
    return `${str}@g.us`;
  }

  // Bersihkan karakter non-digit
  let cleaned = str.replace(/\D/g, '');

  // Ubah awalan lokal 08xxx menjadi 628xxx
  if (cleaned.startsWith('0')) {
    cleaned = '62' + cleaned.substring(1);
  }

  return `${cleaned}@s.whatsapp.net`;
}

// ==========================================
// Session Manager Functions (WAHA Style)
// ==========================================

export async function startSession(sessionId) {
  if (!sessionId) throw new Error('sessionId wajib diisi.');

  const sessionName = String(sessionId).trim();
  const existing = sessions.get(sessionName);

  // Jika sudah aktif atau sedang memulai, gunakan instance yang ada
  if (existing && (existing.status === SessionStatus.WORKING || existing.status === SessionStatus.STARTING) && existing.sock) {
    return existing;
  }

  // Jika ada socket lama yang tertinggal, tutup terlebih dahulu agar tidak conflict 440
  if (existing?.sock) {
    try {
      existing.sock.ev.removeAllListeners();
      existing.sock.end(undefined);
    } catch (_) {}
  }

  const sessionDir = path.resolve(sessionRoot, sessionName);
  if (!fs.existsSync(sessionDir)) {
    fs.mkdirSync(sessionDir, { recursive: true });
  }

  console.log(`[${sessionName}] Memulai sesi WhatsApp...`);

  const sessionObj = {
    name: sessionName,
    status: SessionStatus.STARTING,
    sock: null,
    qr: null,
    latestQR: null,
    user: null,
    updatedAt: new Date(),
    isStopped: false,
    reconnectAttempts: 0,
  };
  sessions.set(sessionName, sessionObj);

  try {
    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: [2, 3000, 1015901307] }));

    const sock = makeWASocket({
      logger: pino({ level: 'debug' }),
      printQRInTerminal: false,
      browser: Browsers.ubuntu('Chrome'),
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, pino({ level: 'silent' })),
      },
      version,
      syncFullHistory: false,
      msgRetryCounterCache: retryCache,
      getMessage: async (key) => {
        const id = key?.id;
        if (!id) return undefined;

        let cached = getMessageFromStore(id);
        if (cached) {
          console.log(`🔄 [RETRY HANDSHAKE] Menemukan pesan di store lokal untuk ID: ${id}`);
          const msg = cached.message || cached;
          try {
            return proto.Message.fromObject(msg);
          } catch (_) {
            return msg;
          }
        }

        // Fallback: Query ke endpoint Sent di Django untuk merekonstruksi pesan teks jika server baru direstart
        try {
          const res = await axios.get(`http://127.0.0.1:8008/whatsapp/api/sent/${id}/`, { timeout: 3000 });
          if (res.data && res.data.message) {
            const rawMsg = res.data.message;
            let text = rawMsg;
            try {
              const parsed = JSON.parse(rawMsg);
              if (parsed && typeof parsed === 'object') {
                text = parsed.text || parsed.message || parsed.body || rawMsg;
              }
            } catch (_) {}

            const reconstructed = { conversation: String(text) };
            saveMessageToStore(id, reconstructed);
            console.log(`🔄 [RETRY HANDSHAKE] Berhasil mengambil pesan dari Django Sent API untuk ID: ${id}`);
            return proto.Message.fromObject(reconstructed);
          }
        } catch (_) {
          // Abaikan jika tidak ditemukan di database
        }

        console.log(`⚠️ [RETRY HANDSHAKE] Pesan tidak ditemukan untuk ID: ${id}`);
        return undefined;
      },
    });

    sessionObj.sock = sock;

    // Simpan credentials otomatis
    sock.ev.on('creds.update', saveCreds);

    // Event Koneksi & QR Code
    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;
      sessionObj.updatedAt = new Date();

      if (qr) {
        sessionObj.status = SessionStatus.SCAN_QR_CODE;
        sessionObj.qr = qr;
        sessionObj.latestQR = qr;
        console.log(`[${sessionName}] QR Code siap di-scan.`);

        // Kirim event webhook
        sendToDjango({
          event: 'session.status',
          session: sessionName,
          status: SessionStatus.SCAN_QR_CODE,
          data: { qr },
        });
        // Kompatibilitas signal Django lama
        sendToDjango({
          event: 'connection.qrcode',
          session: sessionName,
          data: { qr },
        });
      }

      if (connection === 'open') {
        sessionObj.status = SessionStatus.WORKING;
        sessionObj.qr = null;
        sessionObj.latestQR = null;
        sessionObj.user = sock.user;
        sessionObj.reconnectAttempts = 0;
        console.log(`[${sessionName}] WhatsApp terhubung! User:`, sock.user?.id || sock.user?.name);

        sendToDjango({
          event: 'session.status',
          session: sessionName,
          status: SessionStatus.WORKING,
          data: { user: sock.user },
        });
        // Kompatibilitas signal Django lama
        sendToDjango({
          event: 'connection.open',
          session: sessionName,
          data: { user: sock.user },
        });
      }

      if (connection === 'close') {
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        console.log(`[${sessionName}] Koneksi terputus. Kode status:`, statusCode);

        if (statusCode === DisconnectReason.loggedOut || statusCode === 401) {
          sessionObj.status = SessionStatus.STOPPED;
          sessionObj.isStopped = true;
          sessionObj.qr = null;
          console.log(`[${sessionName}] Sesi telah logout / kadaluarsa.`);
          deleteSessionFolder(sessionName);
          sessions.delete(sessionName);

          sendToDjango({
            event: 'session.status',
            session: sessionName,
            status: SessionStatus.STOPPED,
          });
          sendToDjango({
            event: 'connection.close',
            session: sessionName,
            data: { reason: 'logged_out', statusCode },
          });
        } else if (statusCode === DisconnectReason.connectionReplaced || statusCode === 440) {
          sessionObj.status = SessionStatus.STOPPED;
          sessionObj.isStopped = true;
          console.warn(`[${sessionName}] Koneksi digantikan oleh proses/klien lain (kode 440 / conflict). Auto-reconnect dihentikan.`);
          sendToDjango({
            event: 'session.status',
            session: sessionName,
            status: SessionStatus.STOPPED,
          });
          sendToDjango({
            event: 'connection.close',
            session: sessionName,
            data: { reason: 'connection_replaced', statusCode },
          });
        } else if (!sessionObj.isStopped) {
          sessionObj.status = SessionStatus.FAILED;
          sessionObj.reconnectAttempts += 1;
          const delay = Math.min(sessionObj.reconnectAttempts * 2000, 10000);
          console.log(`[${sessionName}] Mencoba menghubungkan kembali dalam ${delay / 1000}s...`);

          setTimeout(() => {
            if (!sessionObj.isStopped) {
              startSession(sessionName).catch(err => {
                console.error(`[${sessionName}] Gagal reconnect:`, err.message);
              });
            }
          }, delay);

          sendToDjango({
            event: 'session.status',
            session: sessionName,
            status: SessionStatus.FAILED,
          });
          sendToDjango({
            event: 'connection.close',
            session: sessionName,
            data: { reason: 'disconnected', statusCode },
          });
        }
      }
    });

    // Handler Pesan Masuk (Inbound Message)
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
      // Simpan semua pesan ke store untuk keperluan retry handshake & reply quote
      for (const m of (messages || [])) {
        if (m?.key?.id && m?.message) {
          saveMessageToStore(m.key.id, m.message, m.key);
          const hasMedia = Boolean(
            m.message?.imageMessage ||
            m.message?.videoMessage ||
            m.message?.viewOnceMessage ||
            m.message?.viewOnceMessageV2
          );
          if (hasMedia) {
            console.log(`💾 [STORE] Menyimpan media message ID: ${m.key.id} (fromMe: ${Boolean(m.key.fromMe)})`);
          }
        }
        if (m?.key?.remoteJid?.includes('@lid') && m?.key?.senderPn) {
          lidMap[m.key.remoteJid] = m.key.senderPn;
          lidMap[m.key.senderPn] = m.key.remoteJid;
          saveLidMap();
        }
      }

      if (type !== 'notify') return;

      for (const msg of (messages || [])) {
        if (!msg || !msg.message) continue;
        if (msg.key.fromMe) continue;

        let sender = msg.key.remoteJid;
        if (msg.key.senderPn) {
          lidMap[msg.key.remoteJid] = msg.key.senderPn;
          saveLidMap();
          sender = msg.key.senderPn;
        } else if (sender && sender.includes('@lid') && lidMap[sender]) {
          sender = lidMap[sender];
        }

        // Unpack viewOnce / ephemeral jika ada untuk deteksi tipe dan teks (mendukung nested multi-layer)
        let innerMsg = normalizeMessageContent(msg.message);
        for (let i = 0; i < 5; i++) {
          const next =
            innerMsg?.viewOnceMessage?.message ||
            innerMsg?.viewOnceMessageV2?.message ||
            innerMsg?.viewOnceMessageV2Extension?.message ||
            innerMsg?.ephemeralMessage?.message ||
            innerMsg?.documentWithCaptionMessage?.message ||
            innerMsg?.editedMessage?.message;
          if (!next) break;
          innerMsg = normalizeMessageContent(next);
        }

        const text =
          innerMsg?.extendedTextMessage?.text ||
          innerMsg?.conversation ||
          innerMsg?.imageMessage?.caption ||
          innerMsg?.videoMessage?.caption ||
          innerMsg?.documentMessage?.caption ||
          '';

        const messageType =
          innerMsg?.imageMessage ? 'imageMessage' :
          innerMsg?.videoMessage ? 'videoMessage' :
          innerMsg?.audioMessage ? 'audioMessage' :
          innerMsg?.documentMessage ? 'documentMessage' :
          innerMsg?.stickerMessage ? 'stickerMessage' :
          innerMsg?.extendedTextMessage ? 'extendedTextMessage' :
          innerMsg?.conversation ? 'conversation' :
          getContentType(innerMsg) ||
          Object.keys(msg.message)[0] || 'conversation';

        const payload = {
          event: 'messages.upsert',
          waha_event: 'message',
          session: sessionName,
          payload: {
            id: msg.key.id,
            from: sender,
            pushName: msg.pushName || 'Unknown',
            body: text,
            type: messageType,
            timestamp: msg.messageTimestamp,
            raw: msg,
          },
          // Fallback properti untuk backward compatibility dengan Django signal on_inbox lama
          data: { messages: [msg] },
          metadata: {
            phone: sessionName,
            sender: sender,
            push_name: msg.pushName,
            text: text,
            message_type: messageType,
          },
          from_me: false,
          message_id: msg.key.id,
          sender: sender,
          push_name: msg.pushName,
          timestamp: msg.messageTimestamp,
          message_type: messageType,
          text: text,
          raw: msg,
        };

        sendToDjango(payload);
        // Kirim event format WAHA standar jika ada consumer eksternal
        sendToDjango({
          ...payload,
          event: 'message',
        });
      }
    });

    return sessionObj;
  } catch (err) {
    sessionObj.status = SessionStatus.FAILED;
    console.error(`[${sessionName}] Gagal memulai sesi:`, err.message);
    throw err;
  }
}

export async function stopSession(sessionId) {
  const sessionName = String(sessionId).trim();
  const session = sessions.get(sessionName);

  if (!session) {
    return { success: false, message: 'Sesi tidak ditemukan atau belum aktif.' };
  }

  session.isStopped = true;
  session.status = SessionStatus.STOPPED;
  session.qr = null;

  if (session.sock) {
    try {
      session.sock.end(undefined);
    } catch (_) {}
  }

  sendToDjango({
    event: 'session.status',
    session: sessionName,
    status: SessionStatus.STOPPED,
  });

  return { success: true, message: `Sesi ${sessionName} berhasil dihentikan.` };
}

export async function logoutSession(sessionId) {
  const sessionName = String(sessionId).trim();
  const session = sessions.get(sessionName);

  if (session && session.sock) {
    try {
      await session.sock.logout();
    } catch (_) {}
    try {
      session.sock.end(undefined);
    } catch (_) {}
  }

  deleteSessionFolder(sessionName);
  sessions.delete(sessionName);

  sendToDjango({
    event: 'session.status',
    session: sessionName,
    status: SessionStatus.STOPPED,
  });

  return { success: true, message: `Sesi ${sessionName} berhasil logout dan dihapus.` };
}

export function getSession(sessionId) {
  const sessionName = String(sessionId).trim();
  return sessions.get(sessionName);
}

export function listSessions() {
  const list = [];
  for (const [name, s] of sessions.entries()) {
    list.push({
      name: s.name,
      status: s.status,
      user: s.user,
      hasQr: !!s.qr,
      updatedAt: s.updatedAt,
    });
  }
  return list;
}

// Auto-Reconnection semua sesi yang ada di folder saat startup
export async function initSessionsFromDisk() {
  if (!fs.existsSync(sessionRoot)) return;

  const entries = fs.readdirSync(sessionRoot, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isDirectory()) {
      const sessionName = entry.name;
      console.log(`[Auto-Start] Memuat sesi tersimpan: ${sessionName}...`);
      try {
        await startSession(sessionName);
        await new Promise(r => setTimeout(r, 1500));
      } catch (err) {
        console.error(`[Auto-Start] Gagal memuat sesi ${sessionName}:`, err.message);
      }
    }
  }
}

// Backward compatibility export untuk fungsi lama
export const connectToWhatsApp = startSession;
export function getAllSessions() {
  return [...sessions.keys()];
}

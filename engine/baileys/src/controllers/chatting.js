import {
  downloadMediaMessage,
  normalizeMessageContent,
  extractMessageContent,
  getContentType,
} from '@whiskeysockets/baileys';
import {
  getSession,
  getAllSessions,
  toJid,
  SessionStatus,
  saveMessageToStore,
  getMessageFromStore,
  getMessageKeyFromStore,
  getQuotedMessage,
  findLatestMediaMessage,
} from '../whatsapp.js';

/**
 * Helper untuk mendapatkan sesi aktif yang valid (dengan fallback pintar)
 */
function resolveWorkingSession(requestedSession) {
  const allSessions = getAllSessions();
  if (allSessions.length === 0) return null;

  // 1. Coba match langsung
  if (requestedSession) {
    const direct = getSession(requestedSession);
    if (direct && direct.status === SessionStatus.WORKING && direct.sock) {
      return direct;
    }
  }

  // 2. Coba cari sesi pertama yang berstatus WORKING
  for (const name of allSessions) {
    const s = getSession(name);
    if (s && s.status === SessionStatus.WORKING && s.sock) {
      return s;
    }
  }

  // 3. Fallback ke sesi pertama yang terdaftar
  return getSession(allSessions[0]);
}

/**
 * Helper untuk mengekstrak atau menyusun objek quoted message (WhatsApp contextInfo)
 */
function resolveQuoted(item, jid) {
  if (!item) return undefined;

  // 1. Jika objek quoted WAMessage sudah lengkap disertakan
  const quoted = item.quoted;
  if (quoted && typeof quoted === 'object' && quoted.key) {
    const clone = { ...quoted, key: { ...quoted.key } };
    if (clone.key.remoteJid) {
      clone.key.remoteJid = toJid(clone.key.remoteJid);
    }
    if (clone.key.participant) {
      clone.key.participant = toJid(clone.key.participant);
    }
    return clone;
  }

  // 2. Jika diberikan ID pesan yang dibalas (reply_to, replyTo, quotedMessageId, messageId, reply)
  const replyTo =
    item.reply_to ||
    item.replyTo ||
    item.quotedMessageId ||
    item.quotedMsg ||
    item.reply ||
    item.messageId;

  if (replyTo && typeof replyTo === 'string') {
    return getQuotedMessage(replyTo.trim(), jid);
  }

  return undefined;
}

/**
 * Helper untuk menyisipkan atau meregenerasi kode refid acak (__ref:xxxxx__)
 */
function attachRefId(messageText, forceNew = false) {
  const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let ref = '';
  for (let i = 0; i < 5; i++) {
    ref += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  const refTag = `__ref:${ref}__`;
  const str = String(messageText ?? '').trim();
  if (/__ref:[a-zA-Z0-9]+__/.test(str)) {
    return forceNew ? str.replace(/__ref:[a-zA-Z0-9]+__/, refTag) : str;
  }
  return str ? `${str}\n\n${refTag}` : refTag;
}

/**
 * Sequential queue per JID untuk mencegah Signal Double Ratchet race conditions
 * saat mengirim banyak pesan berturut-turut ke penerima yang sama.
 */
const jidLocks = new Map();

function enqueueSend(jid, sendFn) {
  const key = String(jid || 'global');
  const prev = jidLocks.get(key) || Promise.resolve();

  const next = prev
    .catch(() => {})
    .then(async () => {
      const res = await sendFn();
      // Jeda 350ms antar pesan ke nomor yang sama agar ratchet Signal selesai sinkronisasi
      await new Promise(r => setTimeout(r, 350));
      return res;
    });

  jidLocks.set(key, next);
  next.finally(() => {
    if (jidLocks.get(key) === next) {
      jidLocks.delete(key);
    }
  });

  return next;
}

/**
 * Controller untuk pengiriman pesan teks ala WAHA (POST /api/sendText)
 * Mendukung format WAHA: { session, chatId, text, reply_to }
 * Mendukung format Array: [{ session, outbox_for, message, reply_to }, ...]
 * Sekaligus fleksibel untuk fallback { phone, to, message, _botDevice, jid, outbox_for }
 */
export async function sendText(req, res) {
  try {
    const items = Array.isArray(req.body) ? req.body : [req.body];
    if (items.length === 0 || !items[0]) {
      return res.status(400).json({ error: 'Body request tidak boleh kosong.' });
    }

    const allResults = [];

    for (const item of items) {
      const requestedSession = item.session || item._botDevice || item.name;
      const session = resolveWorkingSession(requestedSession);

      if (!session || session.status !== SessionStatus.WORKING || !session.sock) {
        return res.status(400).json({
          error: `Sesi '${requestedSession || 'default'}' belum siap atau belum terhubung (status: ${session?.status || 'NOT_FOUND'}).`,
        });
      }

      const rawChatId = item.chatId || item.jid || item.phone || item.to || item.outbox_for || item.recipient;
      const text = item.text ?? item.message;

      if (!rawChatId) {
        return res.status(400).json({ error: "Field 'chatId' atau 'outbox_for' wajib diisi." });
      }
      if (text === undefined || text === null || text === '') {
        return res.status(400).json({ error: "Field 'text' atau 'message' wajib diisi." });
      }

      // Normalisasi list nomor tujuan (bisa array, bisa string dipisah koma)
      let targetList = [];
      if (Array.isArray(rawChatId)) {
        targetList = rawChatId;
      } else if (typeof rawChatId === 'string' && rawChatId.includes(',')) {
        targetList = rawChatId.split(',').map(s => s.trim()).filter(Boolean);
      } else {
        targetList = [rawChatId];
      }

      const sock = session.sock;

      for (const target of targetList) {
        let jid = toJid(target);
        if (!jid) continue;

        // Siapkan opsi reply / quote jika ada
        const quotedMsg = resolveQuoted(item, jid);
        const sendOptions = quotedMsg ? { quoted: quotedMsg } : {};

        // Jika pesan ini adalah balasan (reply) untuk pesan masuk yang berasal dari @lid,
        // kirim langsung ke @lid agar Signal ratchet session tetap sinkron
        if (quotedMsg?.key?.remoteJid?.includes('@lid')) {
          jid = quotedMsg.key.remoteJid;
        } else if (item.remoteJid && item.remoteJid.includes('@lid')) {
          jid = item.remoteJid;
        } else if (item.data?.remoteJid && item.data.remoteJid.includes('@lid')) {
          jid = item.data.remoteJid;
        }

        // Pastikan setiap pesan memiliki refid unik (jika multi-recipient, regenerasi agar tiap nomor beda)
        const textToSend = attachRefId(text, targetList.length > 1);

        try {
          const sent = await enqueueSend(jid, async () => {
            // Simulasi Human-Like (hanya jika simulateTyping bernilai true)
            const shouldSimulateTyping = item.simulateTyping === true;

            if (shouldSimulateTyping) {
              // 1. sendSeen (Centang Biru) jika membalas pesan masuk
              if (quotedMsg?.key) {
                try {
                  await sock.readMessages([quotedMsg.key]);
                } catch (_) {}
              }

              // 2. Kirim presence composing ("sedang mengetik...")
              try {
                await sock.sendPresenceUpdate('composing', jid);
                const delayMs =
                  typeof item.typingDelay === 'number'
                    ? Math.min(Math.max(item.typingDelay, 500), 5000)
                    : 1200;

                await new Promise(r => setTimeout(r, delayMs));
              } catch (e) {
                console.warn('[TYPING] sendPresenceUpdate composing error:', e?.message);
              }
            }

            const sendResult = await sock.sendMessage(jid, { text: textToSend }, sendOptions);
            if (shouldSimulateTyping) {
              try {
                await sock.sendPresenceUpdate('paused', jid);
              } catch (_) {}
            }
            return sendResult;
          });

          // Simpan ke store agar jika WhatsApp meminta retry handshake, bot bisa membalas
          if (sent?.key?.id && sent?.message) {
            saveMessageToStore(sent.key.id, sent.message, sent.key);
          }

          allResults.push({
            success: true,
            id: sent.key.id,
            to: jid,
            timestamp: sent.messageTimestamp,
          });
        } catch (sendErr) {
          allResults.push({
            success: false,
            to: jid,
            error: sendErr.message,
          });
        }
      }
    }

    // Jika hanya 1 pesan ke 1 nomor dan bukan array di root
    if (!Array.isArray(req.body) && allResults.length === 1) {
      const single = allResults[0];
      return single.success ? res.status(200).json(single) : res.status(500).json(single);
    }

    // Jika multiple
    return res.status(200).json({
      success: allResults.some(r => r.success),
      total: allResults.length,
      results: allResults,
    });
  } catch (err) {
    console.error('sendText error:', err);
    return res.status(500).json({ error: `Gagal mengirim pesan: ${err.message}` });
  }
}

/**
 * Controller untuk pengiriman reply pesan ala WAHA / Erpro (POST /api/reply atau POST /api/sendReply)
 * Mendukung body: { session, phone/chatId, message/text, messageId/reply_to }
 */
export async function reply(req, res) {
  const body = req.body || {};
  const messageId =
    body.messageId ||
    body.reply_to ||
    body.replyTo ||
    body.quotedMessageId ||
    body.quotedMsg;

  if (!messageId) {
    return res.status(400).json({ error: "Field 'messageId' atau 'reply_to' wajib diisi untuk melakukan reply." });
  }

  req.body.reply_to = messageId;
  return sendText(req, res);
}

/**
 * Controller untuk pengiriman gambar ala WAHA (POST /api/sendImage)
 */
export async function sendImage(req, res) {
  try {
    const sessionName = req.body.session || req.body._botDevice || req.body.name;
    const session = resolveWorkingSession(sessionName);
    if (!session || session.status !== SessionStatus.WORKING || !session.sock) {
      return res.status(400).json({ error: `Sesi '${sessionName || 'default'}' belum terhubung.` });
    }

    const rawChatId = req.body.chatId || req.body.jid || req.body.phone || req.body.to || req.body.outbox_for;
    if (!rawChatId) {
      return res.status(400).json({ error: "Field 'chatId' wajib diisi." });
    }

    let jid = toJid(rawChatId);
    const rawCaption = req.body.caption || '';
    const caption = rawCaption ? attachRefId(rawCaption) : '';
    const fileUrl = req.body.file?.url || req.body.url || req.body.image;

    if (!fileUrl) {
      return res.status(400).json({ error: "Field 'file.url' atau 'url' wajib diisi." });
    }

    let imagePayload = {};
    if (typeof fileUrl === 'string' && fileUrl.startsWith('http')) {
      imagePayload = { image: { url: fileUrl }, caption };
    } else if (typeof fileUrl === 'string' && fileUrl.startsWith('data:image')) {
      const buffer = Buffer.from(fileUrl.split(',')[1], 'base64');
      imagePayload = { image: buffer, caption };
    } else {
      imagePayload = { image: { url: fileUrl }, caption };
    }

    const quotedMsg = resolveQuoted(req.body, jid);
    const sendOptions = quotedMsg ? { quoted: quotedMsg } : {};

    if (quotedMsg?.key?.remoteJid?.includes('@lid')) {
      jid = quotedMsg.key.remoteJid;
    } else if (req.body.remoteJid && req.body.remoteJid.includes('@lid')) {
      jid = req.body.remoteJid;
    }

    const sent = await enqueueSend(jid, async () => {
      const shouldSimulateTyping = req.body.simulateTyping === true;

      if (shouldSimulateTyping) {
        if (quotedMsg?.key) {
          try {
            await session.sock.readMessages([quotedMsg.key]);
          } catch (_) {}
        }
        try {
          await session.sock.sendPresenceUpdate('composing', jid);
        } catch (_) {}

        await new Promise(r => setTimeout(r, 1000));

        try {
          await session.sock.sendPresenceUpdate('paused', jid);
        } catch (_) {}
      }

      return session.sock.sendMessage(jid, imagePayload, sendOptions);
    });
    if (sent?.key?.id && sent?.message) {
      saveMessageToStore(sent.key.id, sent.message, sent.key);
    }

    return res.status(200).json({
      success: true,
      id: sent.key.id,
      to: jid,
      timestamp: sent.messageTimestamp,
    });
  } catch (err) {
    console.error('sendImage error:', err);
    return res.status(500).json({ error: `Gagal mengirim gambar: ${err.message}` });
  }
}

/**
 * Controller untuk pengiriman file / dokumen ala WAHA (POST /api/sendFile)
 */
export async function sendFile(req, res) {
  try {
    const sessionName = req.body.session || req.body._botDevice || req.body.name;
    const session = resolveWorkingSession(sessionName);
    if (!session || session.status !== SessionStatus.WORKING || !session.sock) {
      return res.status(400).json({ error: `Sesi '${sessionName || 'default'}' belum terhubung.` });
    }

    const rawChatId = req.body.chatId || req.body.jid || req.body.phone || req.body.to || req.body.outbox_for;
    if (!rawChatId) {
      return res.status(400).json({ error: "Field 'chatId' wajib diisi." });
    }

    let jid = toJid(rawChatId);
    const rawCaption = req.body.caption || '';
    const caption = rawCaption ? attachRefId(rawCaption) : '';
    const fileUrl = req.body.file?.url || req.body.url || req.body.document;
    const filename = req.body.file?.filename || req.body.filename || 'document';
    const mimetype = req.body.file?.mimetype || req.body.mimetype || 'application/octet-stream';

    if (!fileUrl) {
      return res.status(400).json({ error: "Field 'file.url' atau 'url' wajib diisi." });
    }

    const documentPayload = {
      document: { url: fileUrl },
      mimetype,
      fileName: filename,
      caption,
    };

    const quotedMsg = resolveQuoted(req.body, jid);
    const sendOptions = quotedMsg ? { quoted: quotedMsg } : {};

    if (quotedMsg?.key?.remoteJid?.includes('@lid')) {
      jid = quotedMsg.key.remoteJid;
    } else if (req.body.remoteJid && req.body.remoteJid.includes('@lid')) {
      jid = req.body.remoteJid;
    }

    const sent = await enqueueSend(jid, () => session.sock.sendMessage(jid, documentPayload, sendOptions));
    if (sent?.key?.id && sent?.message) {
      saveMessageToStore(sent.key.id, sent.message, sent.key);
    }

    return res.status(200).json({
      success: true,
      id: sent.key.id,
      to: jid,
      timestamp: sent.messageTimestamp,
    });
  } catch (err) {
    console.error('sendFile error:', err);
    return res.status(500).json({ error: `Gagal mengirim dokumen: ${err.message}` });
  }
}

/**
 * Controller untuk mengunduh dan mendekripsi media dari pesan (termasuk View Once)
 * POST /api/downloadMedia
 */
function unwrapMedia(msg) {
  if (!msg) return null;
  let unwrapped = normalizeMessageContent(msg.message || msg);
  for (let i = 0; i < 5; i++) {
    const next =
      unwrapped?.viewOnceMessage?.message ||
      unwrapped?.viewOnceMessageV2?.message ||
      unwrapped?.viewOnceMessageV2Extension?.message ||
      unwrapped?.ephemeralMessage?.message ||
      unwrapped?.documentWithCaptionMessage?.message ||
      unwrapped?.editedMessage?.message;
    if (!next) break;
    unwrapped = normalizeMessageContent(next);
  }
  return unwrapped;
}

function getMediaInfo(msg) {
  const unwrapped = unwrapMedia(msg);
  if (!unwrapped) return null;
  return (
    unwrapped.imageMessage ||
    unwrapped.videoMessage ||
    unwrapped.audioMessage ||
    unwrapped.documentMessage ||
    unwrapped.stickerMessage ||
    null
  );
}

function hasMediaKeys(msg) {
  const media = getMediaInfo(msg);
  if (!media) return false;
  const hasUrl = Boolean(media.url || media.directPath || media.thumbnailDirectPath);
  const hasKey = Boolean(
    media.mediaKey &&
    (Buffer.isBuffer(media.mediaKey) ||
      (typeof media.mediaKey === 'object' && (media.mediaKey.data || media.mediaKey.type === 'Buffer')) ||
      (Array.isArray(media.mediaKey) && media.mediaKey.length > 0) ||
      (typeof media.mediaKey === 'string' && media.mediaKey.length > 0))
  );
  return hasUrl && hasKey;
}

function restoreMediaBuffers(media) {
  if (!media || typeof media !== 'object') return media;
  for (const key of ['mediaKey', 'fileSha256', 'fileEncSha256', 'jpegThumbnail']) {
    const val = media[key];
    if (val && !Buffer.isBuffer(val)) {
      if (val.type === 'Buffer' && Array.isArray(val.data)) {
        media[key] = Buffer.from(val.data);
      } else if (Array.isArray(val)) {
        media[key] = Buffer.from(val);
      } else if (typeof val === 'string' && /^[A-Za-z0-9+/=]+$/.test(val)) {
        media[key] = Buffer.from(val, 'base64');
      }
    }
  }
  return media;
}

export async function downloadMedia(req, res) {
  try {
    const sessionName = req.body.session || req.body._botDevice || req.body.name;
    const session = resolveWorkingSession(sessionName);
    if (!session || session.status !== SessionStatus.WORKING || !session.sock) {
      return res.status(400).json({ error: `Sesi '${sessionName || 'default'}' belum terhubung.` });
    }

    let messageObj = req.body.message;
    const messageId = req.body.messageId || req.body.id || messageObj?.key?.id;

    // Prioritaskan pesan dari store lokal jika ID tersedia dan store memiliki kunci media lengkap
    if (messageId) {
      const cached = getMessageFromStore(messageId);
      const cachedKey = getMessageKeyFromStore(messageId);
      if (cached) {
        const cachedInner = cached.message || cached;
        if (hasMediaKeys(cachedInner) || !hasMediaKeys(messageObj)) {
          messageObj = {
            key: { ...(cachedKey || {}), ...(messageObj?.key || {}), id: messageId },
            message: cachedInner,
          };
        }
      }
    }

    if (!messageObj) {
      return res.status(400).json({ error: "Field 'message' atau 'messageId' wajib diisi." });
    }

    // Unwrap jika pesan dibungkus dalam bentuk viewOnceMessage / ephemeralMessage
    let unwrapped = unwrapMedia(messageObj);

    // Fallback: Jika kunci enkripsi tidak ada pada objek pesan (misal quoted view-once),
    // cari pesan media terakhir di chat/grup ini yang tersimpan di memori/disk store
    if (!hasMediaKeys(unwrapped)) {
      const chatId = req.body.chatId || messageObj?.key?.remoteJid;
      const participant = req.body.participant || messageObj?.key?.participant;
      if (chatId) {
        const found = findLatestMediaMessage(chatId, participant);
        if (found && found.message && hasMediaKeys(unwrapMedia(found.message))) {
          console.log(`[downloadMedia] Fallback berhasil: menemukan media terakhir untuk ${chatId} (ID: ${found.key?.id})`);
          messageObj = found;
          unwrapped = unwrapMedia(messageObj.message);
        }
      }
    }

    if (!hasMediaKeys(unwrapped)) {
      return res.status(404).json({
        error:
          'Kunci enkripsi media tidak ditemukan (mediaKey / url kosong). Pastikan pesan sekali lihat dikirim ke bot / grup saat bot sedang aktif agar bot dapat mencatat kunci dekripsinya. (Catatan: WhatsApp tidak menyinkronkan kunci view-once yang dikirim langsung dari aplikasi WhatsApp HP bot ke perangkat tertaut).',
      });
    }

    const targetMsg = {
      key: messageObj.key || { id: messageId || 'dummy_id' },
      message: unwrapped,
    };

    const mContent = extractMessageContent(targetMsg.message) || targetMsg.message;
    const contentType = getContentType(mContent) || Object.keys(mContent || {})[0] || '';
    const mediaInfo = mContent ? mContent[contentType] : {};
    restoreMediaBuffers(mediaInfo);

    const buffer = await downloadMediaMessage(
      targetMsg,
      'buffer',
      {},
      {
        reuploadRequest: session.sock.updateMediaMessage,
        logger: session.sock.logger,
      }
    );

    if (!buffer || buffer.length === 0) {
      return res.status(404).json({ error: 'Gagal mengunduh media atau media kosong.' });
    }

    // Tentukan mimetype dan tipe media
    const mimetype = mediaInfo?.mimetype || (contentType.includes('video') ? 'video/mp4' : 'image/jpeg');

    let mediaType = 'image';
    if (mimetype.startsWith('video/')) mediaType = 'video';
    else if (mimetype.startsWith('audio/')) mediaType = 'audio';
    else if (!mimetype.startsWith('image/')) mediaType = 'file';

    const ext = mimetype.split('/')[1]?.split(';')[0] || (mediaType === 'video' ? 'mp4' : mediaType === 'image' ? 'jpeg' : 'bin');
    const base64Data = `data:${mimetype};base64,${buffer.toString('base64')}`;

    return res.status(200).json({
      success: true,
      type: mediaType,
      mimetype: mimetype,
      filename: mediaInfo?.fileName || `view_once_${Date.now()}.${ext}`,
      data: base64Data,
      size: buffer.length,
    });
  } catch (err) {
    console.error('downloadMedia error:', err);
    return res.status(500).json({ error: `Gagal mendekripsi media: ${err.message}` });
  }
}

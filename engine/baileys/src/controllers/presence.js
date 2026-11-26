import {
  getSession,
  getAllSessions,
  toJid,
  SessionStatus,
} from '../whatsapp.js';

/**
 * Helper untuk mendapatkan sesi aktif yang valid
 */
function resolveWorkingSession(requestedSession) {
  const allSessions = getAllSessions();
  if (allSessions.length === 0) return null;

  if (requestedSession) {
    const direct = getSession(requestedSession);
    if (direct && direct.status === SessionStatus.WORKING && direct.sock) {
      return direct;
    }
  }

  for (const name of allSessions) {
    const s = getSession(name);
    if (s && s.status === SessionStatus.WORKING && s.sock) {
      return s;
    }
  }

  return getSession(allSessions[0]);
}

/**
 * POST /api/sendSeen
 * Menandai pesan sebagai "Sudah Dibaca" (Centang Biru / Read Receipt)
 */
export async function sendSeen(req, res) {
  try {
    const sessionName = req.body.session || req.body._botDevice || req.body.name;
    const session = resolveWorkingSession(sessionName);
    if (!session || session.status !== SessionStatus.WORKING || !session.sock) {
      return res.status(400).json({ error: `Sesi '${sessionName || 'default'}' belum terhubung.` });
    }

    const rawChatId = req.body.chatId || req.body.jid || req.body.phone || req.body.to;
    if (!rawChatId) {
      return res.status(400).json({ error: "Field 'chatId' wajib diisi." });
    }

    const jid = toJid(rawChatId);
    const messageId = req.body.messageId || req.body.id;
    const participant = req.body.participant ? toJid(req.body.participant) : undefined;

    if (messageId) {
      const key = {
        remoteJid: jid,
        id: String(messageId).trim(),
        participant,
      };
      await session.sock.readMessages([key]);
    } else {
      // Jika tidak diberikan messageId, kirim tanda baca umum untuk chat
      await session.sock.sendReceipt(jid, participant, undefined, 'read').catch(() => {});
    }

    return res.status(200).json({
      success: true,
      message: `Chat ${jid} berhasil ditandai telah dibaca (seen).`,
    });
  } catch (err) {
    console.error('sendSeen error:', err);
    return res.status(500).json({ error: `Gagal mengirim status seen: ${err.message}` });
  }
}

/**
 * POST /api/startTyping
 * Menampilkan status "sedang mengetik..." (composing) di layar WhatsApp lawan bicara
 */
export async function startTyping(req, res) {
  try {
    const sessionName = req.body.session || req.body._botDevice || req.body.name;
    const session = resolveWorkingSession(sessionName);
    if (!session || session.status !== SessionStatus.WORKING || !session.sock) {
      return res.status(400).json({ error: `Sesi '${sessionName || 'default'}' belum terhubung.` });
    }

    const rawChatId = req.body.chatId || req.body.jid || req.body.phone || req.body.to;
    if (!rawChatId) {
      return res.status(400).json({ error: "Field 'chatId' wajib diisi." });
    }

    const jid = toJid(rawChatId);
    await session.sock.sendPresenceUpdate('composing', jid);

    return res.status(200).json({
      success: true,
      message: `Status typing (sedang mengetik) aktif untuk ${jid}.`,
    });
  } catch (err) {
    console.error('startTyping error:', err);
    return res.status(500).json({ error: `Gagal mengaktifkan typing: ${err.message}` });
  }
}

/**
 * POST /api/stopTyping
 * Menghentikan status "sedang mengetik..." (paused)
 */
export async function stopTyping(req, res) {
  try {
    const sessionName = req.body.session || req.body._botDevice || req.body.name;
    const session = resolveWorkingSession(sessionName);
    if (!session || session.status !== SessionStatus.WORKING || !session.sock) {
      return res.status(400).json({ error: `Sesi '${sessionName || 'default'}' belum terhubung.` });
    }

    const rawChatId = req.body.chatId || req.body.jid || req.body.phone || req.body.to;
    if (!rawChatId) {
      return res.status(400).json({ error: "Field 'chatId' wajib diisi." });
    }

    const jid = toJid(rawChatId);
    await session.sock.sendPresenceUpdate('paused', jid);

    return res.status(200).json({
      success: true,
      message: `Status typing dihentikan untuk ${jid}.`,
    });
  } catch (err) {
    console.error('stopTyping error:', err);
    return res.status(500).json({ error: `Gagal menghentikan typing: ${err.message}` });
  }
}

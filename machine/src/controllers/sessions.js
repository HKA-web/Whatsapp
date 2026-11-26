import QRCode from 'qrcode';
import {
  startSession,
  stopSession,
  logoutSession,
  getSession,
  listSessions,
  SessionStatus,
} from '../whatsapp.js';

/**
 * GET /api/sessions
 * Mengambil daftar seluruh sesi aktif beserta statusnya
 */
export async function getSessions(req, res) {
  try {
    const sessions = listSessions();
    return res.status(200).json(sessions);
  } catch (err) {
    console.error('getSessions error:', err);
    return res.status(500).json({ error: err.message });
  }
}

/**
 * POST /api/sessions/start atau POST /api/sessions
 * Memulai sesi baru untuk nomor tertentu
 * Body: { name: "6285648007953" }
 */
export async function startSessionHandler(req, res) {
  try {
    const sessionName = req.body.name || req.body.session || req.query.name || req.query.phone;
    if (!sessionName) {
      return res.status(400).json({ error: "Field 'name' (nomor sesi) wajib diisi." });
    }

    const sessionObj = await startSession(sessionName);

    return res.status(200).json({
      success: true,
      name: sessionObj.name,
      status: sessionObj.status,
      message: `Inisialisasi sesi '${sessionName}' berhasil dimulai.`,
    });
  } catch (err) {
    console.error('startSessionHandler error:', err);
    return res.status(500).json({ error: `Gagal memulai sesi: ${err.message}` });
  }
}

/**
 * POST /api/sessions/stop
 * Menghentikan sesi aktif
 * Body: { name: "6285648007953" }
 */
export async function stopSessionHandler(req, res) {
  try {
    const sessionName = req.body.name || req.body.session || req.params.session || req.query.name;
    if (!sessionName) {
      return res.status(400).json({ error: "Field 'name' wajib diisi." });
    }

    const result = await stopSession(sessionName);
    return res.status(200).json(result);
  } catch (err) {
    console.error('stopSessionHandler error:', err);
    return res.status(500).json({ error: err.message });
  }
}

/**
 * POST /api/sessions/logout
 * Logout resmi dan hapus folder sesi di disk
 * Body: { name: "6285648007953" }
 */
export async function logoutSessionHandler(req, res) {
  try {
    const sessionName = req.body.name || req.body.session || req.params.session || req.query.name;
    if (!sessionName) {
      return res.status(400).json({ error: "Field 'name' wajib diisi." });
    }

    const result = await logoutSession(sessionName);
    return res.status(200).json(result);
  } catch (err) {
    console.error('logoutSessionHandler error:', err);
    return res.status(500).json({ error: err.message });
  }
}

/**
 * GET /api/:session/auth/qr
 * Menampilkan QR Code sesi langsung sebagai gambar PNG (atau JSON jika ?format=json)
 */
export async function getQrCodeHandler(req, res) {
  try {
    const sessionName = req.params.session || req.query.session || req.query.phone;
    if (!sessionName) {
      return res.status(400).json({ error: 'Parameter sesi wajib diisi.' });
    }

    let session = getSession(sessionName);
    if (!session || session.status === SessionStatus.STOPPED) {
      console.log(`[QR-Handler] Sesi '${sessionName}' belum aktif di memori, otomatis memulai startSession...`);
      session = await startSession(sessionName);
      let waited = 0;
      while (!session.qr && !session.latestQR && waited < 5000 && session.status !== SessionStatus.WORKING) {
        await new Promise(r => setTimeout(r, 500));
        waited += 500;
      }
    }

    if (!session) {
      return res.status(404).json({ error: `Sesi '${sessionName}' belum dibuat atau tidak aktif.` });
    }

    if (session.status === SessionStatus.WORKING) {
      return res.status(200).json({
        status: session.status,
        message: 'Sesi sudah terhubung (tidak memerlukan scan QR).',
      });
    }

    const qrData = session.qr || session.latestQR;
    if (!qrData) {
      return res.status(202).json({
        status: session.status,
        message: 'QR Code belum tersedia atau sedang dimuat, silakan muat ulang.',
      });
    }

    // Format response JSON jika diminta
    if (req.query.format === 'json') {
      return res.status(200).json({
        status: session.status,
        qr: qrData,
      });
    }

    // Default: Kirim buffer gambar PNG langsung
    const pngBuffer = await QRCode.toBuffer(qrData, {
      type: 'png',
      width: 320,
      margin: 2,
    });

    res.writeHead(200, {
      'Content-Type': 'image/png',
      'Content-Length': pngBuffer.length,
      'Cache-Control': 'no-cache, no-store, must-revalidate',
    });
    return res.end(pngBuffer);
  } catch (err) {
    console.error('getQrCodeHandler error:', err);
    return res.status(500).json({ error: `Gagal memuat QR Code: ${err.message}` });
  }
}

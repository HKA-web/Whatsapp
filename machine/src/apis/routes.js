import { Router } from 'express';

// Controller standar WAHA & Reply (Single Source of Truth)
import { sendText, sendImage, sendFile, reply, downloadMedia } from '../controllers/chatting.js';
import { sendSeen, startTyping, stopTyping } from '../controllers/presence.js';
import {
  getSessions,
  startSessionHandler,
  stopSessionHandler,
  logoutSessionHandler,
  getQrCodeHandler,
} from '../controllers/sessions.js';

const router = Router();

/* ========================================================
 * 1. STANDAR CHATTING & REPLY API (Single Truth)
 * ======================================================== */
router.post('/sendText', sendText);
router.post('/sendImage', sendImage);
router.post('/sendFile', sendFile);
router.post('/downloadMedia', downloadMedia);
router.post('/media/download', downloadMedia);

// Endpoint Reply ala Erpro & WAHA
router.post('/reply', reply);
router.post('/sendReply', reply);
router.post('/message/reply', reply);
router.post('/:session/message/reply', (req, res, next) => {
  req.body = req.body || {};
  req.body.session = req.params.session;
  return reply(req, res, next);
});

/* ========================================================
 * 2. STANDAR WAHA SESSION MANAGEMENT API
 * ======================================================== */
router.get('/sessions', getSessions);
router.post('/sessions', startSessionHandler);
router.post('/sessions/start', startSessionHandler);
router.post('/sessions/stop', stopSessionHandler);
router.post('/sessions/logout', logoutSessionHandler);

// Endpoint QR Code (standar WAHA /api/{session}/auth/qr)
router.get('/:session/auth/qr', getQrCodeHandler);

/* ========================================================
 * 3. STANDAR WAHA PRESENCE & SEEN API
 * ======================================================== */
router.post('/sendSeen', sendSeen);
router.post('/startTyping', startTyping);
router.post('/stopTyping', stopTyping);

export default router;

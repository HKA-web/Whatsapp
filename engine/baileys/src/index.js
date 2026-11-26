import express from 'express';
import fs from 'fs';
import path from 'path';
import multer from 'multer';
import swaggerUi from 'swagger-ui-express';
import bodyParser from 'body-parser';
import cors from 'cors';
import os from 'os';
import { fileURLToPath } from 'url';
import { initSessionsFromDisk } from './whatsapp.js';
import route from './apis/routes.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function getSwaggerFilePath() {
  const candidates = [
    path.resolve(__dirname, '../openapi.json'),               // whatsapp/machine/openapi.json (dari src atau dist)
    path.resolve(__dirname, './openapi.json'),
    path.join(process.cwd(), 'whatsapp/engine/baileys/openapi.json'), // jika dijalankan dari root microservice
    path.join(process.cwd(), 'openapi.json'),                  // jika dijalankan dari dalam whatsapp/machine
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return path.resolve(__dirname, '../openapi.json');
}

function loadSwaggerDocument() {
  const swaggerFilePath = getSwaggerFilePath();
  try {
    if (fs.existsSync(swaggerFilePath)) {
      return JSON.parse(fs.readFileSync(swaggerFilePath, 'utf-8'));
    }
  } catch (err) {
    console.error('[SWAGGER] Gagal membaca openapi.json:', err?.message || err);
  }
  return null;
}

// Global error handlers agar proses tidak crash saat terjadi disconnect/reconnect Baileys
process.on('uncaughtException', (err) => {
  console.error('[CRITICAL] Uncaught Exception:', err?.message || err);
});
process.on('unhandledRejection', (reason) => {
  console.error('[CRITICAL] Unhandled Rejection:', reason?.message || reason);
});

const app = express();
const upload = multer();

// CORS supaya bisa diakses IP luar
app.use(cors({ origin: '*', methods: ['GET', 'POST', 'PUT', 'DELETE'], allowedHeaders: ['Content-Type', 'Authorization'] }));

// Endpoint raw openapi.json (selalu membaca file terbaru dari disk tanpa cache)
app.get('/openapi.json', (req, res) => {
  res.set('Cache-Control', 'no-store, no-cache, must-revalidate, private');
  res.set('Pragma', 'no-cache');
  res.set('Expires', '0');
  const doc = loadSwaggerDocument();
  if (doc) {
    return res.json(doc);
  }
  const swaggerFilePath = getSwaggerFilePath();
  if (fs.existsSync(swaggerFilePath)) {
    return res.sendFile(swaggerFilePath);
  }
  return res.status(404).json({ error: 'openapi.json tidak ditemukan', path: swaggerFilePath });
});

// Swagger Docs (Disajikan langsung dengan spec OpenAPI agar tidak bergantung pada network fetch browser)
app.use(
  '/docs',
  (req, res, next) => {
    res.set('Cache-Control', 'no-store, no-cache, must-revalidate, private');
    res.set('Pragma', 'no-cache');
    res.set('Expires', '0');
    next();
  },
  swaggerUi.serve,
  (req, res, next) => {
    const doc = loadSwaggerDocument() || {};
    swaggerUi.setup(doc)(req, res, next);
  }
);

// Middleware
app.use(bodyParser.json({ limit: '100mb' }));
app.use(express.urlencoded({ extended: true, limit: '100mb' }));
app.use(upload.none());

// Root redirect ke Swagger Docs
app.get('/', (req, res) => res.redirect('/docs'));

// Single Source of Truth API Routes
app.use('/api', route);

// Auto reconnect sesi yang tersimpan di disk
initSessionsFromDisk();

function getLocalIP() {
  const nets = os.networkInterfaces();
  for (const name of Object.keys(nets)) {
    for (const net of nets[name]) {
      if (net.family === 'IPv4' && !net.internal) return net.address;
    }
  }
  return '0.0.0.0';
}

const portArg = process.argv.find(arg => arg.startsWith('--port='));
const webhookArg = process.argv.find(arg => arg.startsWith('--webhook.url='));
if (webhookArg && !process.env.WEBHOOK_URL) {
  process.env.WEBHOOK_URL = webhookArg.split('=')[1];
}

const PORT = process.env.PORT || (portArg ? portArg.split('=')[1] : null) || 3002;
const HOST = '0.0.0.0';

app.listen(PORT, HOST, () => {
  console.log(`🚀 WhatsApp Microservice berjalan di port: ${PORT}`);
  console.log(`Local:        http://localhost:${PORT}`);
  console.log(`Network:      http://${getLocalIP()}:${PORT}`);
  console.log(`Swagger Docs: http://localhost:${PORT}/docs`);
  if (process.env.WEBHOOK_URL) {
    console.log(`Webhook URL:  ${process.env.WEBHOOK_URL}`);
  }
});

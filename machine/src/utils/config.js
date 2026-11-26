import yaml from 'js-yaml';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { z } from 'zod';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const filePath = path.resolve('../../erpro.yaml');

export function sleep(ms = process.env.config_delay ?? 500) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export async function sendChunk(
  text,
  sendFunc,
  maxCharsPerBatch = Math.min(process.env.config_maxChar ?? 4000, 4000),
  delayMs = process.env.config_delay ?? 500,
  mode = process.env.config_sendChunkMode || 'auto'
) {
  let chunks = [];

  if (mode === 'auto') {
    mode = text.includes('\n') ? 'char' : 'word';
  }

  if (mode === 'word') {
    const words = text.split(/\s+/);
    let buffer = '';
    for (const word of words) {
      if ((buffer + ' ' + word).trim().length > maxCharsPerBatch) {
        chunks.push(buffer.trim());
        buffer = word;
      } else {
        buffer += ' ' + word;
      }
    }
    if (buffer.trim().length > 0) chunks.push(buffer.trim());
  } else {
    for (let i = 0; i < text.length; i += maxCharsPerBatch) {
      chunks.push(text.slice(i, i + maxCharsPerBatch));
    }
  }

  for (const chunk of chunks) {
    await sendFunc(chunk);
    if (delayMs > 0) await sleep(delayMs);
  }
}

export function trimStrings(obj) {
  if (Array.isArray(obj)) return obj.map(trimStrings);
  if (obj && typeof obj === 'object') {
    const newObj = {};
    for (const key in obj) {
      if (typeof obj[key] === 'string') newObj[key] = obj[key].trim();
      else if (Array.isArray(obj[key]) || typeof obj[key] === 'object') newObj[key] = trimStrings(obj[key]);
      else newObj[key] = obj[key];
    }
    return newObj;
  }
  return obj;
}

export function generateSchemaFromRow(row) {
  const schema = [];
  for (const key in row) {
    const value = row[key];
    let type = 'any';

    if (value === null || value === undefined) type = 'any';
    else if (typeof value === 'string') type = 'string';
    else if (typeof value === 'number') type = 'number';
    else if (value instanceof Date) type = 'date';
    else if (typeof value === 'boolean') type = 'boolean';

    schema.push({ name: key, type });
  }
  return schema;
}

export function mapRowsWithSchema(rows) {
  if (!rows || rows.length === 0) return { schema: [], data: [] };

  const schema = generateSchemaFromRow(rows[0]);
  const data = rows.map(row => {
    const obj = {};
    for (const col of schema) {
      let value = row[col.name];
      if (col.type === 'string' && typeof value === 'string') value = value.trim();
      if (col.type === 'date' && value) value = new Date(value);
      obj[col.name] = value;
    }
    return obj;
  });

  return { schema, data };
}

export function mapRowsDynamic(rows) {
  if (!rows || rows.length === 0) return [];
  const schema = generateSchemaFromRow(rows[0]);
  return rows.map(row => {
    const obj = {};
    for (const col of schema) {
      let value = row[col.name];
      if (col.type === 'string' && typeof value === 'string') value = value.trim();
      if (col.type === 'date' && value) value = new Date(value);
      obj[col.name] = value;
    }
    return obj;
  });
}

export function deleteSessionFolder(phoneNumber) {
  try {
    const candidateDirs = [
      path.resolve(__dirname, '../../sessions', phoneNumber),
      path.resolve(__dirname, '../sessions', phoneNumber),
      path.resolve(__dirname, 'sessions', phoneNumber),
      path.resolve(process.cwd(), 'whatsapp/machine/sessions', phoneNumber),
      path.resolve(process.cwd(), 'whatsapp/machine/src/sessions', phoneNumber),
      path.resolve(process.cwd(), 'whatsapp/machine/dist/sessions', phoneNumber),
    ];
    for (const sessionDir of candidateDirs) {
      if (fs.existsSync(sessionDir)) {
        fs.rmSync(sessionDir, { recursive: true, force: true });
        console.log(`[${phoneNumber}] Folder session dihapus: ${sessionDir}`);
      }
    }
  } catch (err) {
    console.error(`[${phoneNumber}] Gagal menghapus session:`, err.message);
  }
}

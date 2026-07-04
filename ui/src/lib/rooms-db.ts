import Database from 'better-sqlite3'
import path from 'path'
import fs from 'fs'

const DATA_DIR = path.join(process.cwd(), '.data')
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true })

const db = new Database(path.join(DATA_DIR, 'rooms.db'))
db.pragma('journal_mode = WAL')
db.pragma('foreign_keys = ON')

db.exec(`
  CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );
  CREATE INDEX IF NOT EXISTS idx_chat_room ON chat_messages(room_id, created_at);

  CREATE TABLE IF NOT EXISTS room_memory (
    room_id TEXT PRIMARY KEY,
    memory TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
  );
`)

export function insertChat(
  roomId: string,
  role: 'user' | 'assistant' | 'system',
  content: string,
  metadata?: Record<string, unknown>
) {
  db.prepare(
    'INSERT INTO chat_messages (room_id, role, content, metadata) VALUES (?, ?, ?, ?)'
  ).run(roomId, role, content, metadata ? JSON.stringify(metadata) : null)
}

export function getChat(roomId: string, limit = 100) {
  return db
    .prepare(
      'SELECT id, role, content, metadata, created_at FROM chat_messages WHERE room_id = ? ORDER BY created_at ASC LIMIT ?'
    )
    .all(roomId, limit) as {
    id: number
    role: string
    content: string
    metadata: string | null
    created_at: string
  }[]
}

export function setMemory(roomId: string, memory: string) {
  db.prepare(
    `INSERT INTO room_memory (room_id, memory, updated_at) VALUES (?, ?, datetime('now'))
     ON CONFLICT(room_id) DO UPDATE SET memory = excluded.memory, updated_at = excluded.updated_at`
  ).run(roomId, memory)
}

export function getMemory(roomId: string): string {
  const row = db
    .prepare('SELECT memory FROM room_memory WHERE room_id = ?')
    .get(roomId) as { memory: string } | undefined
  return row?.memory ?? ''
}

export function getAllMemory(): { room_id: string; memory: string; updated_at: string }[] {
  return db.prepare('SELECT room_id, memory, updated_at FROM room_memory').all() as {
    room_id: string
    memory: string
    updated_at: string
  }[]
}

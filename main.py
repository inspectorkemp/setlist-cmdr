"""
Setlist CMDR — Raspberry Pi Local Server
Run with: uvicorn main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import os
import shutil

DB_PATH = "setlist.db"

# ──────────────────────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS songs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            artist      TEXT,
            song_key    TEXT,
            tempo       INTEGER,
            duration    INTEGER,
            status      TEXT DEFAULT 'active',
            lyrics      TEXT,
            chords      TEXT,
            notes       TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS setlists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            description TEXT,
            active      INTEGER DEFAULT 1,
            position    INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS setlist_songs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            setlist_id    INTEGER NOT NULL,
            song_id       INTEGER NOT NULL,
            position      INTEGER NOT NULL,
            section_label TEXT,
            FOREIGN KEY (setlist_id) REFERENCES setlists(id),
            FOREIGN KEY (song_id)    REFERENCES songs(id)
        );
    """)
    conn.commit()
    # Migrations for existing databases
    try:
        conn.execute("ALTER TABLE setlists ADD COLUMN active INTEGER DEFAULT 1")
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE setlists ADD COLUMN position INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass
    conn.close()

# ──────────────────────────────────────────────────────────────
# Live state  (kept in memory — resets on server restart)
# ──────────────────────────────────────────────────────────────

live_state = {
    "setlist_id":        None,
    "setlist_name":      None,
    "song_index":        0,
    "is_live":           False,
}

# ──────────────────────────────────────────────────────────────
# WebSocket connection manager
# ──────────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: dict[WebSocket, str] = {}   # ws → name

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active[ws] = ""   # name registered later

    def disconnect(self, ws: WebSocket):
        self.active.pop(ws, None)

    def set_name(self, ws: WebSocket, name: str):
        if ws in self.active:
            self.active[ws] = name

    def roster(self) -> list[str]:
        """Return only named musicians (blank = leader/anonymous, excluded)."""
        return [n for n in self.active.values() if n]

    def count(self):
        return len(self.active)

    async def broadcast(self, msg: dict):
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_roster(self):
        await self.broadcast({
            "type":      "roster_update",
            "count":     self.count(),
            "musicians": self.roster(),
        })

manager = ConnectionManager()

# ──────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────

app = FastAPI(title="Setlist CMDR")
init_db()
os.makedirs("static", exist_ok=True)

# ── Pydantic models ───────────────────────────────────────────

class SongIn(BaseModel):
    title:    str
    artist:   Optional[str] = None
    song_key: Optional[str] = None
    tempo:    Optional[int] = None
    duration: Optional[int] = None
    status:   str = "active"
    lyrics:   Optional[str] = None
    chords:   Optional[str] = None
    notes:    Optional[str] = None

class SetlistIn(BaseModel):
    name:        str
    description: Optional[str] = None
    active:      Optional[int] = None  # 1=active, 0=inactive

class SetlistReorderIn(BaseModel):
    order: List[int]   # setlist IDs in new order

class SetlistSongIn(BaseModel):
    song_id:       int
    position:      int
    section_label: Optional[str] = None

class ReorderIn(BaseModel):
    order: List[int]   # setlist_song row IDs in new order

class LiveIn(BaseModel):
    setlist_id:   Optional[int] = None
    setlist_name: Optional[str] = None
    song_index:   int  = 0
    is_live:      bool = False

# ── Songs ─────────────────────────────────────────────────────

@app.get("/api/songs")
def list_songs(status: Optional[str] = None):
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM songs WHERE status=? ORDER BY title", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM songs ORDER BY title").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/songs", status_code=201)
def create_song(song: SongIn):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO songs (title,artist,song_key,tempo,duration,status,lyrics,chords,notes)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (song.title, song.artist, song.song_key, song.tempo, song.duration,
         song.status, song.lyrics, song.chords, song.notes)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM songs WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)

@app.get("/api/songs/{song_id}")
def get_song(song_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Song not found")
    return dict(row)

@app.put("/api/songs/{song_id}")
def update_song(song_id: int, song: SongIn):
    conn = get_db()
    conn.execute(
        "UPDATE songs SET title=?,artist=?,song_key=?,tempo=?,duration=?,status=?,"
        "lyrics=?,chords=?,notes=? WHERE id=?",
        (song.title, song.artist, song.song_key, song.tempo, song.duration,
         song.status, song.lyrics, song.chords, song.notes, song_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    conn.close()
    return dict(row)

@app.delete("/api/songs/{song_id}")
def delete_song(song_id: int):
    conn = get_db()
    conn.execute("DELETE FROM setlist_songs WHERE song_id=?", (song_id,))
    conn.execute("DELETE FROM songs WHERE id=?", (song_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

# ── Setlists ──────────────────────────────────────────────────

@app.get("/api/setlists")
def list_setlists():
    conn = get_db()
    rows = conn.execute("SELECT * FROM setlists ORDER BY position ASC, created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/setlists", status_code=201)
def create_setlist(sl: SetlistIn):
    conn = get_db()
    max_pos = conn.execute("SELECT COALESCE(MAX(position),0) FROM setlists").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO setlists (name,description,active,position) VALUES (?,?,1,?)",
        (sl.name, sl.description, max_pos + 1)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM setlists WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)

@app.put("/api/setlists/reorder")
def reorder_setlists(body: SetlistReorderIn):
    conn = get_db()
    for i, sl_id in enumerate(body.order):
        conn.execute("UPDATE setlists SET position=? WHERE id=?", (i, sl_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.put("/api/setlists/{sl_id}")
def update_setlist(sl_id: int, sl: SetlistIn):
    conn = get_db()
    if sl.active is not None:
        conn.execute(
            "UPDATE setlists SET name=?,description=?,active=? WHERE id=?",
            (sl.name, sl.description, sl.active, sl_id)
        )
    else:
        conn.execute(
            "UPDATE setlists SET name=?,description=? WHERE id=?",
            (sl.name, sl.description, sl_id)
        )
    conn.commit()
    row = conn.execute("SELECT * FROM setlists WHERE id=?", (sl_id,)).fetchone()
    conn.close()
    return dict(row)

@app.delete("/api/setlists/{sl_id}")
def delete_setlist(sl_id: int):
    conn = get_db()
    conn.execute("DELETE FROM setlist_songs WHERE setlist_id=?", (sl_id,))
    conn.execute("DELETE FROM setlists WHERE id=?", (sl_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/api/setlists/{sl_id}/clone", status_code=201)
def clone_setlist(sl_id: int):
    conn = get_db()
    original = conn.execute("SELECT * FROM setlists WHERE id=?", (sl_id,)).fetchone()
    if not original:
        conn.close()
        raise HTTPException(404, "Setlist not found")
    new_name = original["name"] + " (copy)"
    cur = conn.execute(
        "INSERT INTO setlists (name,description) VALUES (?,?)",
        (new_name, original["description"])
    )
    new_id = cur.lastrowid
    songs = conn.execute(
        "SELECT song_id, position, section_label FROM setlist_songs WHERE setlist_id=? ORDER BY position",
        (sl_id,)
    ).fetchall()
    for s in songs:
        conn.execute(
            "INSERT INTO setlist_songs (setlist_id,song_id,position,section_label) VALUES (?,?,?,?)",
            (new_id, s["song_id"], s["position"], s["section_label"])
        )
    conn.commit()
    row = conn.execute("SELECT * FROM setlists WHERE id=?", (new_id,)).fetchone()
    conn.close()
    return dict(row)

@app.get("/api/setlists/{sl_id}/songs")
def get_setlist_songs(sl_id: int):
    conn = get_db()
    rows = conn.execute("""
        SELECT ss.id as ss_id, ss.position, ss.section_label, s.*
        FROM setlist_songs ss
        JOIN songs s ON ss.song_id = s.id
        WHERE ss.setlist_id = ?
        ORDER BY ss.position
    """, (sl_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/setlists/{sl_id}/songs", status_code=201)
def add_song_to_setlist(sl_id: int, entry: SetlistSongIn):
    conn = get_db()
    # find max position
    row = conn.execute(
        "SELECT MAX(position) as mp FROM setlist_songs WHERE setlist_id=?", (sl_id,)
    ).fetchone()
    pos = (row["mp"] or -1) + 1
    conn.execute(
        "INSERT INTO setlist_songs (setlist_id,song_id,position,section_label) VALUES (?,?,?,?)",
        (sl_id, entry.song_id, pos, entry.section_label)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.put("/api/setlists/{sl_id}/reorder")
def reorder_songs(sl_id: int, body: ReorderIn):
    conn = get_db()
    for i, ss_id in enumerate(body.order):
        conn.execute(
            "UPDATE setlist_songs SET position=? WHERE id=? AND setlist_id=?",
            (i, ss_id, sl_id)
        )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/api/setlists/{sl_id}/songs/{ss_id}")
def remove_from_setlist(sl_id: int, ss_id: int):
    conn = get_db()
    conn.execute("DELETE FROM setlist_songs WHERE id=? AND setlist_id=?", (ss_id, sl_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.put("/api/setlists/{sl_id}/songs/{ss_id}/section")
def set_section_label(sl_id: int, ss_id: int, body: dict):
    conn = get_db()
    conn.execute(
        "UPDATE setlist_songs SET section_label=? WHERE id=? AND setlist_id=?",
        (body.get("label"), ss_id, sl_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

# ── Live state ────────────────────────────────────────────────

@app.get("/api/live")
def get_live():
    return {**live_state, "musicians": manager.count(), "roster": manager.roster()}

@app.get("/api/musicians")
def get_musicians():
    return {"count": manager.count(), "musicians": manager.roster()}

@app.put("/api/live")
async def set_live(state: LiveIn):
    live_state.update(state.dict())
    await manager.broadcast({"type": "live_update", **live_state})
    return live_state

# ── Metro state (in-memory) ───────────────────────────────────
metro_state = {
    "on":           False,
    "bpm":          None,
    "beats_per_bar": 4,
    "server_epoch": None,   # ms timestamp of beat 0
}

@app.put("/api/metro")
async def set_metro_stub():
    return {"ok": True}

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    import time, json
    await manager.connect(websocket)
    await websocket.send_json({"type": "live_update", **live_state})
    # Send current metro state to newly connected client
    if metro_state["on"]:
        await websocket.send_json({"type": "metronome_start", **metro_state})
    await manager.broadcast_roster()
    try:
        while True:
            data = await websocket.receive_text()

            # NTP-style clock sync: client sends {"type":"sync","t0":clientMs}
            if data.startswith("{"):
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "sync":
                        server_now = time.time() * 1000
                        await websocket.send_json({
                            "type":    "sync_reply",
                            "t0":      msg["t0"],
                            "server":  server_now,
                        })
                    elif msg.get("type") == "metronome_start":
                        # Leader broadcasting start to all musicians
                        metro_state.update({
                            "on":            True,
                            "bpm":           msg["bpm"],
                            "beats_per_bar": msg.get("beats_per_bar", 4),
                            "server_epoch":  msg["server_epoch"],
                        })
                        await manager.broadcast({
                            "type":         "metronome_start",
                            "bpm":          metro_state["bpm"],
                            "beats_per_bar": metro_state["beats_per_bar"],
                            "server_epoch": metro_state["server_epoch"],
                        })
                    elif msg.get("type") == "metronome_stop":
                        metro_state["on"] = False
                        metro_state["server_epoch"] = None
                        await manager.broadcast({"type": "metronome_stop"})
                except Exception:
                    pass
            elif data.startswith("name:"):
                manager.set_name(websocket, data[5:].strip()[:40])
                await manager.broadcast_roster()
            # else: keep-alive ping — ignore
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast_roster()

# ── Static / pages ────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    r = FileResponse("static/musician.html")
    r.headers["Cache-Control"] = "no-store"
    return r

@app.get("/leader")
def leader_page():
    r = FileResponse("static/leader.html")
    r.headers["Cache-Control"] = "no-store"
    return r

@app.get("/sw.js")
def service_worker():
    r = FileResponse("static/sw.js", media_type="application/javascript")
    r.headers["Cache-Control"] = "no-cache"  # SW must always be re-checked
    return r

@app.get("/manifest.json")
def manifest():
    r = FileResponse("static/manifest.json", media_type="application/manifest+json")
    r.headers["Cache-Control"] = "no-cache"
    return r

class SignalIn(BaseModel):
    text: str

@app.post("/api/signal")
async def send_signal(sig: SignalIn):
    if not sig.text.strip():
        raise HTTPException(400, "Signal text cannot be empty")
    await manager.broadcast({"type": "signal", "text": sig.text.strip()})
    return {"ok": True}

@app.get("/api/db/download")
def download_db():
    if not os.path.exists(DB_PATH):
        raise HTTPException(404, "Database not found")
    from datetime import datetime
    filename = f"setlist-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    r = FileResponse(DB_PATH, media_type="application/octet-stream", filename=filename)
    r.headers["Cache-Control"] = "no-store"
    return r

@app.post("/api/db/upload")
async def upload_db(file: UploadFile = File(...)):
    from datetime import datetime
    tmp_path = DB_PATH + ".tmp"
    # Read entire file into memory so we hold no file handles during OS operations
    data = await file.read()
    await file.close()

    # Validate SQLite magic bytes
    if not data[:16].startswith(b"SQLite format 3"):
        raise HTTPException(400, "File is not a valid SQLite database")

    # Clean up any leftover tmp from a previous failed attempt
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    try:
        # Write to temp path
        with open(tmp_path, "wb") as f:
            f.write(data)

        # Validate schema — open, check, close
        conn = sqlite3.connect(tmp_path)
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        finally:
            conn.close()

        required = {"songs", "setlists", "setlist_songs"}
        missing = required - tables
        if missing:
            os.remove(tmp_path)
            raise HTTPException(400, f"Database is missing required tables: {', '.join(missing)}")

        # Back up current db
        if os.path.exists(DB_PATH):
            backup = DB_PATH + f".bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            shutil.copy2(DB_PATH, backup)

        # Replace — os.replace is atomic and works on Windows
        os.replace(tmp_path, DB_PATH)

        # Run migrations in case uploaded db has older schema
        init_db()
        return {"ok": True, "message": "Database replaced successfully"}

    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise HTTPException(500, f"Upload failed: {str(e)}")

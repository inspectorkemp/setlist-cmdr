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
import hashlib
import secrets
import time
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

DB_PATH = "setlist.db"

# ──────────────────────────────────────────────────────────────
# Build ID — hash of the key static files.
# Changes whenever files are updated. Used to bust all caches.
# ──────────────────────────────────────────────────────────────
def _compute_build_id():
    h = hashlib.md5()
    for fname in ["static/leader.html", "static/musician.html",
                  "static/leader.css", "static/sw.js"]:
        try:
            with open(fname, "rb") as f:
                h.update(f.read())
        except FileNotFoundError:
            pass
    return h.hexdigest()[:10]

BUILD_ID = _compute_build_id()


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
            capo        INTEGER DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS app_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS band_members (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL UNIQUE,
            position INTEGER DEFAULT 0
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
    # capo column — migrate existing databases
    try:
        conn.execute("ALTER TABLE songs ADD COLUMN capo INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass
    # band_members added in 2025 — create if missing on older databases
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS band_members (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT NOT NULL UNIQUE,
                position INTEGER DEFAULT 0
            )
        """)
        conn.commit()
    except Exception:
        pass
    conn.close()

# ──────────────────────────────────────────────────────────────
# Live state  (persisted to DB so server restarts are transparent)
# ──────────────────────────────────────────────────────────────

import json as _json

def _save_state(key: str, value: dict):
    """Persist a state dict to app_state table."""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
        (key, _json.dumps(value))
    )
    conn.commit()
    conn.close()

def _load_state(key: str, default: dict) -> dict:
    """Load a state dict from app_state table, returning default if missing.
    Safe to call before init_db() — returns default if table does not exist yet."""
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
        conn.close()
        if row:
            try:
                return _json.loads(row[0])
            except Exception:
                pass
    except Exception:
        pass
    return dict(default)

# Load persisted state on startup (falls back to defaults if first run)
live_state = _load_state("live_state", {
    "setlist_id":   None,
    "setlist_name": None,
    "song_index":   0,
    "is_live":      False,
})

rehearsal_state = _load_state("rehearsal_state", {
    "active": False,
    "song":   None,
})

def _validate_live_state():
    """
    Called after init_db(). If the persisted live state references a setlist
    that no longer exists, reset to not-live rather than serve stale data.
    Rehearsal state with an embedded song needs no validation.
    """
    if not live_state.get("is_live"):
        return
    sl_id = live_state.get("setlist_id")
    if sl_id is None:
        # Rehearsal mode with embedded song — valid, leave it
        return
    conn = get_db()
    row = conn.execute("SELECT id FROM setlists WHERE id=?", (sl_id,)).fetchone()
    conn.close()
    if not row:
        # Setlist was deleted — reset gracefully
        live_state.update({
            "setlist_id": None, "setlist_name": None,
            "song_index": 0, "is_live": False
        })
        _save_state("live_state", live_state)

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
# Auth — PIN-based sessions
# ──────────────────────────────────────────────────────────────

# In-memory sessions: token -> expiry epoch
_sessions: dict[str, float] = {}
_SESSION_TTL = 86400  # 24 hours
_bearer = HTTPBearer(auto_error=False)

def _get_pin() -> str:
    """Return the configured PIN from app_state, defaulting to 1234."""
    conn = get_db()
    row  = conn.execute("SELECT value FROM app_state WHERE key='leader_pin'").fetchone()
    conn.close()
    return row[0] if row else "1234"

def _set_pin(new_pin: str):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO app_state (key,value) VALUES ('leader_pin',?)", (new_pin,))
    conn.commit()
    conn.close()

def _new_token() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + _SESSION_TTL
    return token

def _valid_token(token: str) -> bool:
    exp = _sessions.get(token)
    if exp is None:
        return False
    if time.time() > exp:
        _sessions.pop(token, None)
        return False
    return True

async def require_auth(creds: HTTPAuthorizationCredentials = Depends(_bearer)):
    token = creds.credentials if creds else None
    if not token or not _valid_token(token):
        raise HTTPException(401, "Unauthorized")

# ──────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────

app = FastAPI(title="Setlist CMDR")

def _seed_demo_data():
    """Populate demo songs and a sample setlist on a brand-new empty database.
    Skips silently if any songs already exist."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    if count > 0:
        conn.close()
        return

    songs = [
        {
            "title":    "Come Together",
            "artist":   "The Beatles",
            "song_key": "Dm",
            "tempo":    82,
            "duration": 259,
            "status":   "active",
            "lyrics":   "Here come old flat top\nHe come grooving up slowly\nHe got joo joo eyeball\nHe one holy roller\nHe got hair down to his knee\nGot to be a joker he just do what he please\n\nHe wear no shoeshine\nHe got toe jam football\nHe got monkey finger\nHe shoot Coca Cola\nHe say I know you, you know me\nOne thing I can tell you is you got to be free\nCome together, right now\nOver me",
            "chords":   "[Dm]Here come old flat top\nHe come grooving up [A]slowly\nHe got [Dm]joo joo eyeball\nHe [A]one holy roller\nHe got [Dm]hair down to his knee\nGot to be a joker he just [A]do what he please\n\n[Dm]He wear no shoeshine\nHe got [A]toe jam football\nHe got [Dm]monkey finger\nHe [A]shoot Coca Cola\nHe say [Dm]I know you, you know me\nOne thing I can tell you is you got to be [A]free\n[D]Come together, [A]right now\n[Dm]Over me",
            "notes":    "Key riff on bass. Slow groove, keep it loose.",
        },
        {
            "title":    "Wonderwall",
            "artist":   "Oasis",
            "song_key": "F#m",
            "tempo":    87,
            "duration": 258,
            "status":   "active",
            "lyrics":   "Today is gonna be the day\nThat they're gonna throw it back to you\nBy now you should've somehow\nRealized what you gotta do\nI don't believe that anybody\nFeels the way I do about you now\n\nAnd after all, you're my wonderwall",
            "chords":   "[Em7]Today is gonna be the day\nThat they're gonna throw it [G]back to you\n[Dsus4]By now you should've somehow\n[A7sus4]Realized what you gotta do\n[Em7]I don't believe that anybody\n[G]Feels the way I [Dsus4]do about [A7sus4]you now\n\nBecause [Em7]maybe, [G]you're gonna be the one that [Dsus4]saves me\n[A7sus4]And after all, [Em7]you're my [G]wonderwall [Dsus4][A7sus4]",
            "notes":    "Capo 2. Em7=022033, G=320033, Dsus4=xx0233, A7sus4=x02030.",
        },
        {
            "title":    "Hotel California",
            "artist":   "Eagles",
            "song_key": "Bm",
            "tempo":    75,
            "duration": 391,
            "status":   "active",
            "lyrics":   "On a dark desert highway\nCool wind in my hair\nWarm smell of colitas\nRising up through the air\n\nWelcome to the Hotel California\nSuch a lovely place, such a lovely face\nPlenty of room at the Hotel California\nAny time of year, you can find it here",
            "chords":   "[Bm]On a dark desert [F#]highway\n[A]Cool wind in my [E]hair\n[G]Warm smell of [D]colitas\n[Em]Rising up through the [F#]air\n\n[G]Welcome to the Hotel [D]California\n[F#]Such a lovely place, such a [Bm]lovely face\n[G]Plenty of room at the Hotel [D]California\n[Em]Any time of year, [F#]you can find it here",
            "notes":    "Iconic 12-string guitar intro. Long outro solo.",
        },
        {
            "title":    "Sweet Home Chicago",
            "artist":   "Robert Johnson",
            "song_key": "E",
            "tempo":    120,
            "duration": 185,
            "status":   "active",
            "lyrics":   "Oh baby, don't you want to go\nBack to the land of California\nTo my sweet home Chicago\n\nNow one and one is two\nTwo and two is four\nCome on baby don't you want to go\nBack to my sweet home Chicago",
            "chords":   "[E7]Oh baby, don't you want to go\n[A7]Back to the land of California\n[E7]To my sweet home [B7]Chicago\n\n[E7]Now one and one is two\n[A7]Two and two is four\n[A7]Come on baby don't you want to go\n[B7]To my sweet home [E7]Chicago",
            "notes":    "12-bar blues in E. Standard shuffle feel.",
        },
    ]

    song_ids = []
    for s in songs:
        cur = conn.execute(
            """INSERT INTO songs (title, artist, song_key, tempo, duration,
               status, lyrics, chords, notes) VALUES (?,?,?,?,?,?,?,?,?)""",
            (s["title"], s["artist"], s["song_key"], s["tempo"], s["duration"],
             s["status"], s["lyrics"], s["chords"], s["notes"])
        )
        song_ids.append(cur.lastrowid)

    cur = conn.execute(
        "INSERT INTO setlists (name, description, active, position) VALUES (?,?,1,0)",
        ("Sample Set", "Demo setlist")
    )
    sl_id = cur.lastrowid
    for pos, sid in enumerate(song_ids[:2]):
        conn.execute(
            "INSERT INTO setlist_songs (setlist_id, song_id, position) VALUES (?,?,?)",
            (sl_id, sid, pos)
        )
    conn.commit()
    conn.close()
init_db()
_validate_live_state()
_seed_demo_data()
os.makedirs("static", exist_ok=True)

# ── Pydantic models ───────────────────────────────────────────

class AuthIn(BaseModel):
    pin: str

class PinChangeIn(BaseModel):
    new_pin: str

class BandMemberIn(BaseModel):
    name: str

class SongIn(BaseModel):
    title:    str
    artist:   Optional[str] = None
    song_key: Optional[str] = None
    capo:     Optional[int] = 0
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

class RehearsalIn(BaseModel):
    song_id: int

class RehearsalDeployIn(BaseModel):
    song_id: int

# ── Auth ──────────────────────────────────────────────────────

@app.post("/api/auth")
def login(body: AuthIn):
    if body.pin != _get_pin():
        raise HTTPException(401, "Incorrect PIN")
    return {"token": _new_token()}

@app.put("/api/auth/pin", dependencies=[Depends(require_auth)])
def change_pin(body: PinChangeIn):
    if not body.new_pin or len(body.new_pin) < 4:
        raise HTTPException(400, "PIN must be at least 4 characters")
    _set_pin(body.new_pin)
    # Invalidate all existing sessions so everyone re-authenticates
    _sessions.clear()
    return {"ok": True}

@app.get("/api/auth/status")
def auth_status():
    """Returns whether a PIN has been explicitly set (vs still the default)."""
    conn = get_db()
    row  = conn.execute("SELECT value FROM app_state WHERE key='leader_pin'").fetchone()
    conn.close()
    return {"pin_is_default": row is None}

# ── Band members ───────────────────────────────────────────────

@app.get("/api/band_members")
def list_band_members():
    conn = get_db()
    rows = conn.execute("SELECT * FROM band_members ORDER BY position, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/band_members", dependencies=[Depends(require_auth)])
def add_band_member(body: BandMemberIn):
    name = body.name.strip()[:40]
    if not name:
        raise HTTPException(400, "Name required")
    conn = get_db()
    try:
        conn.execute("INSERT INTO band_members (name) VALUES (?)", (name,))
        conn.commit()
        row = conn.execute("SELECT * FROM band_members WHERE name=?", (name,)).fetchone()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, "Name already exists")
    conn.close()
    return dict(row)

@app.delete("/api/band_members/{member_id}", dependencies=[Depends(require_auth)])
def delete_band_member(member_id: int):
    conn = get_db()
    conn.execute("DELETE FROM band_members WHERE id=?", (member_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.put("/api/band_members/reorder", dependencies=[Depends(require_auth)])
def reorder_band_members(body: ReorderIn):
    conn = get_db()
    for pos, mid in enumerate(body.order):
        conn.execute("UPDATE band_members SET position=? WHERE id=?", (pos, mid))
    conn.commit()
    conn.close()
    return {"ok": True}

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

@app.post("/api/songs", status_code=201, dependencies=[Depends(require_auth)])
def create_song(song: SongIn):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO songs (title,artist,song_key,capo,tempo,duration,status,lyrics,chords,notes)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (song.title, song.artist, song.song_key, song.capo or 0, song.tempo, song.duration,
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

@app.put("/api/songs/{song_id}", dependencies=[Depends(require_auth)])
def update_song(song_id: int, song: SongIn):
    conn = get_db()
    conn.execute(
        "UPDATE songs SET title=?,artist=?,song_key=?,capo=?,tempo=?,duration=?,status=?,"
        "lyrics=?,chords=?,notes=? WHERE id=?",
        (song.title, song.artist, song.song_key, song.capo or 0, song.tempo, song.duration,
         song.status, song.lyrics, song.chords, song.notes, song_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    conn.close()
    return dict(row)

@app.delete("/api/songs/{song_id}", dependencies=[Depends(require_auth)])
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

@app.post("/api/setlists", status_code=201, dependencies=[Depends(require_auth)])
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

@app.put("/api/setlists/reorder", dependencies=[Depends(require_auth)])
def reorder_setlists(body: SetlistReorderIn):
    conn = get_db()
    for i, sl_id in enumerate(body.order):
        conn.execute("UPDATE setlists SET position=? WHERE id=?", (i, sl_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.put("/api/setlists/{sl_id}", dependencies=[Depends(require_auth)])
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

@app.delete("/api/setlists/{sl_id}", dependencies=[Depends(require_auth)])
def delete_setlist(sl_id: int):
    conn = get_db()
    conn.execute("DELETE FROM setlist_songs WHERE setlist_id=?", (sl_id,))
    conn.execute("DELETE FROM setlists WHERE id=?", (sl_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/api/setlists/{sl_id}/clone", status_code=201, dependencies=[Depends(require_auth)])
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

@app.post("/api/setlists/{sl_id}/songs", status_code=201, dependencies=[Depends(require_auth)])
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

@app.put("/api/setlists/{sl_id}/reorder", dependencies=[Depends(require_auth)])
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

@app.delete("/api/setlists/{sl_id}/songs/{ss_id}", dependencies=[Depends(require_auth)])
def remove_from_setlist(sl_id: int, ss_id: int):
    conn = get_db()
    conn.execute("DELETE FROM setlist_songs WHERE id=? AND setlist_id=?", (ss_id, sl_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.put("/api/setlists/{sl_id}/songs/{ss_id}/section", dependencies=[Depends(require_auth)])
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

@app.put("/api/live", dependencies=[Depends(require_auth)])
async def set_live(state: LiveIn):
    live_state.update(state.dict())
    _save_state("live_state", live_state)
    await manager.broadcast({"type": "live_update", **live_state})
    return live_state

# ── Rehearsal ─────────────────────────────────────────────────

@app.post("/api/rehearsal/deploy", dependencies=[Depends(require_auth)])
async def deploy_rehearsal(body: RehearsalDeployIn):
    """Sets is_live=True with a single song embedded. No setlist needed."""
    conn = get_db()
    row = conn.execute("SELECT * FROM songs WHERE id=?", (body.song_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Song not found")
    song = dict(row)
    live_state.update({
        "setlist_id":   None,
        "setlist_name": "REHEARSAL",
        "song_index":   0,
        "is_live":      True,
        "song":         song,   # embedded directly — no setlist fetch needed
    })
    rehearsal_state["active"] = True
    rehearsal_state["song"]   = song
    _save_state("rehearsal_state", rehearsal_state)
    _save_state("live_state", live_state)
    await manager.broadcast({"type": "live_update", **live_state})
    return {"ok": True, "song": song}

@app.get("/api/rehearsal")
def get_rehearsal():
    return rehearsal_state

@app.post("/api/rehearsal", dependencies=[Depends(require_auth)])
async def start_rehearsal(body: RehearsalIn):
    conn = get_db()
    row = conn.execute("SELECT * FROM songs WHERE id=?", (body.song_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Song not found")
    rehearsal_state["active"] = True
    rehearsal_state["song"]   = dict(row)
    _save_state("rehearsal_state", rehearsal_state)
    await manager.broadcast({"type": "rehearsal_update", "song": rehearsal_state["song"]})
    return rehearsal_state

@app.delete("/api/rehearsal", dependencies=[Depends(require_auth)])
async def stop_rehearsal():
    rehearsal_state["active"] = False
    rehearsal_state["song"]   = None
    _save_state("rehearsal_state", rehearsal_state)
    await manager.broadcast({"type": "rehearsal_stop"})
    return {"ok": True}

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
    # Send current rehearsal state to newly connected client
    if rehearsal_state["active"] and rehearsal_state["song"]:
        await websocket.send_json({"type": "rehearsal_update", "song": rehearsal_state["song"]})
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
                    elif msg.get("type") == "scroll_update":
                        # Leader scroll position — forward to all monitors
                        await manager.broadcast({
                            "type": "scroll_update",
                            "pct":  msg.get("pct", 0),
                        })
                    elif msg.get("type") == "transpose_update":
                        await manager.broadcast({
                            "type": "transpose_update",
                            "xp":   msg.get("xp", 0),
                        })
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

@app.get("/fonts.css")
def serve_fonts_css():
    """Serve locally cached font CSS if setup-fonts.sh has been run,
    otherwise redirect to Google Fonts so the app always works."""
    local = os.path.join("static", "fonts", "fonts.css")
    if os.path.exists(local):
        return FileResponse(local, media_type="text/css",
                           headers={"Cache-Control": "public, max-age=86400"})
    from fastapi.responses import RedirectResponse
    return RedirectResponse(
        "https://fonts.googleapis.com/css2?family=Bebas+Neue"
        "&family=DM+Mono:ital,wght@0,300;0,400;0,500"
        "&family=DM+Sans:wght@400;500;600;700&display=swap"
    )

def _inject_build(html: str) -> str:
    """Replace the placeholder CSS version and inject BUILD_ID meta tag."""
    # Bust the CSS link regardless of whatever ?v= value is in the file
    import re
    html = re.sub(r'/static/leader\.css(\?v=[^"]*)?', f'/static/leader.css?v={BUILD_ID}', html)
    # Inject a meta tag so the SW and JS can read the build ID
    meta = f'<meta charset="UTF-8">\n<meta name="build-id" content="{BUILD_ID}">'
    html = html.replace('<meta charset="UTF-8">', meta)
    return html

@app.get("/monitor")
def monitor():
    r = FileResponse("static/monitor.html")
    r.headers["Cache-Control"] = "no-store"
    return r

@app.get("/")
def root():
    with open("static/musician.html", encoding="utf-8") as f:
        html = _inject_build(f.read())
    return Response(html, media_type="text/html",
                    headers={"Cache-Control": "no-store"})

@app.get("/leader")
def leader_page():
    with open("static/leader.html", encoding="utf-8") as f:
        html = _inject_build(f.read())
    return Response(html, media_type="text/html",
                    headers={"Cache-Control": "no-store"})

@app.get("/api/version")
def get_version():
    return {"build": BUILD_ID}

@app.get("/sw.js")
def service_worker():
    r = FileResponse("static/sw.js", media_type="application/javascript")
    r.headers["Cache-Control"] = "no-cache"
    return r

@app.get("/manifest.json")
def manifest():
    r = FileResponse("static/manifest.json", media_type="application/manifest+json")
    r.headers["Cache-Control"] = "no-cache"
    return r

class SignalIn(BaseModel):
    text: str

@app.post("/api/signal", dependencies=[Depends(require_auth)])
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

@app.post("/api/db/upload", dependencies=[Depends(require_auth)])
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

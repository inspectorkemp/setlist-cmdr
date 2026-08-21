"""
Setlist CMDR — Raspberry Pi Local Server
Run with: uvicorn main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Request
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
import re
import io
import socket
import uuid
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

DB_PATH = "setlist.db"

# ──────────────────────────────────────────────────────────────
# Build ID — hash of the key static files.
# Changes whenever files are updated. Used to bust all caches.
# ──────────────────────────────────────────────────────────────
def _compute_build_id():
    h = hashlib.md5()
    try:
        for root, _, files in os.walk("static"):
            for fname in sorted(files):
                if fname.endswith((".html", ".css", ".js", ".json")):
                    try:
                        with open(os.path.join(root, fname), "rb") as f:
                            h.update(f.read())
                    except (FileNotFoundError, PermissionError):
                        pass
    except FileNotFoundError:
        pass
    return h.hexdigest()[:10]

BUILD_ID = _compute_build_id()


# ──────────────────────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────────────────────

from contextlib import contextmanager

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# ──────────────────────────────────────────────────────────────
# Schema migrations
# Each entry is (version: int, description: str, fn: callable(conn)).
# Migrations run in version order. The highest applied version is
# stored in app_state under key 'schema_version'.
# Adding a new column/table: append a new entry — never edit existing ones.
# ──────────────────────────────────────────────────────────────

def _schema_version(conn) -> int:
    """Return the current schema version, or 0 if never set."""
    try:
        row = conn.execute(
            "SELECT value FROM app_state WHERE key='schema_version'"
        ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0

def _set_schema_version(conn, version: int):
    conn.execute(
        "INSERT OR REPLACE INTO app_state (key, value) VALUES ('schema_version', ?)",
        (str(version),)
    )
    conn.commit()

def _col_exists(conn, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)

def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None

# ── Migration definitions ─────────────────────────────────────

def _m001_base_schema(conn):
    """Create all base tables if they don't exist."""
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
    """)
    conn.commit()

def _m002_setlist_active_position(conn):
    """Add active and position columns to setlists."""
    if not _col_exists(conn, 'setlists', 'active'):
        conn.execute("ALTER TABLE setlists ADD COLUMN active INTEGER DEFAULT 1")
    if not _col_exists(conn, 'setlists', 'position'):
        conn.execute("ALTER TABLE setlists ADD COLUMN position INTEGER DEFAULT 0")
    conn.commit()

def _m003_band_members(conn):
    """Add band_members table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS band_members (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL UNIQUE,
            position INTEGER DEFAULT 0
        )
    """)
    conn.commit()

def _m004_songs_capo(conn):
    """Add capo column to songs."""
    if not _col_exists(conn, 'songs', 'capo'):
        conn.execute("ALTER TABLE songs ADD COLUMN capo INTEGER DEFAULT 0")
    conn.commit()

def _m005_songs_time_sig(conn):
    """Add time_sig column to songs."""
    if not _col_exists(conn, 'songs', 'time_sig'):
        conn.execute("ALTER TABLE songs ADD COLUMN time_sig TEXT DEFAULT '4/4'")
    conn.commit()

# ── Migration registry — append only, never edit existing entries ─
_MIGRATIONS = [
    (1, "Base schema",                   _m001_base_schema),
    (2, "Setlist active/position",       _m002_setlist_active_position),
    (3, "Band members table",            _m003_band_members),
    (4, "Songs capo column",             _m004_songs_capo),
    (5, "Songs time_sig column",         _m005_songs_time_sig),
]

def init_db():
    """Run all pending migrations in version order."""
    with get_db() as conn:

        # Ensure app_state exists before we try to read schema_version from it.
        # This is the one bootstrapping step that must run unconditionally.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()

        current = _schema_version(conn)

        pending = [(v, desc, fn) for v, desc, fn in _MIGRATIONS if v > current]
        if pending:
            for version, desc, fn in pending:
                try:
                    fn(conn)
                    _set_schema_version(conn, version)
                    print(f"[DB] Migration {version}: {desc} — applied")
                except Exception as exc:
                    print(f"[DB] Migration {version}: {desc} — FAILED: {exc}")
                    raise RuntimeError(
                        f"Database migration {version} ('{desc}') failed: {exc}. "
                        "The database may be in a partial state. "
                        "Restore from a backup before restarting."
                    ) from exc
        else:
            print(f"[DB] Schema up to date (version {current})")


# ──────────────────────────────────────────────────────────────
# Live state  (persisted to DB so server restarts are transparent)
# ──────────────────────────────────────────────────────────────

import json as _json

def _save_state(key: str, value: dict):
    """Persist a state dict to app_state table."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
            (key, _json.dumps(value))
        )
        conn.commit()

def _load_state(key: str, default: dict) -> dict:
    """Load a state dict from app_state table, returning default if missing.
    Safe to call before init_db() — returns default if table does not exist yet."""
    try:
        with get_db() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
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
    with get_db() as conn:
        row = conn.execute("SELECT id FROM setlists WHERE id=?", (sl_id,)).fetchone()
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
        self.monitor_ids: dict[WebSocket, str] = {}  # ws → monitor_id (only set for identified monitor connections)

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active[ws] = ""   # name registered later

    def disconnect(self, ws: WebSocket):
        self.active.pop(ws, None)
        self.monitor_ids.pop(ws, None)

    def set_name(self, ws: WebSocket, name: str):
        if ws in self.active:
            self.active[ws] = name

    def set_monitor_id(self, ws: WebSocket, monitor_id: str):
        self.monitor_ids[ws] = monitor_id

    def monitor_connected(self, monitor_id: str) -> bool:
        return monitor_id in self.monitor_ids.values()

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

    async def send_to_monitor(self, monitor_id: str, msg: dict):
        """Send a message only to connections identified as this specific
        monitor — not a global broadcast. A monitor may (rarely) have more
        than one live connection (e.g. a reload in flight); all get it."""
        dead = []
        for ws, mid in list(self.monitor_ids.items()):
            if mid != monitor_id:
                continue
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

# Sessions: token -> expiry epoch. Persisted so they survive restarts.
_sessions: dict[str, float] = {}
_SESSION_TTL = 86400  # 24 hours

def _load_sessions():
    import json as _j
    try:
        with get_db() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key='_sessions'").fetchone()
            if row:
                now = time.time()
                _sessions.update({k: v for k, v in _j.loads(row[0]).items() if v > now})
    except Exception:
        pass

def _persist_sessions():
    import json as _j
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_state (key, value) VALUES ('_sessions', ?)",
                (_j.dumps(_sessions),)
            )
            conn.commit()
    except Exception:
        pass
_bearer = HTTPBearer(auto_error=False)

def _get_pin() -> str:
    """Return the configured PIN from app_state, defaulting to 1234."""
    with get_db() as conn:
        row  = conn.execute("SELECT value FROM app_state WHERE key='leader_pin'").fetchone()
    return row[0] if row else "1234"

def _set_pin(new_pin: str):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO app_state (key,value) VALUES ('leader_pin',?)", (new_pin,))
        conn.commit()

def _new_token() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + _SESSION_TTL
    _persist_sessions()
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
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
        if count > 0:
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
init_db()
_validate_live_state()
_seed_demo_data()
_load_sessions()
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
    time_sig: Optional[str] = "4/4"
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
    _persist_sessions()
    return {"ok": True}

@app.get("/api/auth/status")
def auth_status():
    """Returns whether a PIN has been explicitly set (vs still the default)."""
    with get_db() as conn:
        row  = conn.execute("SELECT value FROM app_state WHERE key='leader_pin'").fetchone()
    return {"pin_is_default": row is None}

# ── Band members ───────────────────────────────────────────────

@app.get("/api/band_members")
def list_band_members():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM band_members ORDER BY position, name").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/band_members", dependencies=[Depends(require_auth)])
def add_band_member(body: BandMemberIn):
    name = body.name.strip()[:40]
    if not name:
        raise HTTPException(400, "Name required")
    with get_db() as conn:
        try:
            conn.execute("INSERT INTO band_members (name) VALUES (?)", (name,))
            conn.commit()
            row = conn.execute("SELECT * FROM band_members WHERE name=?", (name,)).fetchone()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Name already exists")
    return dict(row)

@app.delete("/api/band_members/{member_id}", dependencies=[Depends(require_auth)])
def delete_band_member(member_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM band_members WHERE id=?", (member_id,))
        conn.commit()
    return {"ok": True}

@app.put("/api/band_members/reorder", dependencies=[Depends(require_auth)])
def reorder_band_members(body: ReorderIn):
    with get_db() as conn:
        for pos, mid in enumerate(body.order):
            conn.execute("UPDATE band_members SET position=? WHERE id=?", (pos, mid))
        conn.commit()
    return {"ok": True}

# ── Songs ─────────────────────────────────────────────────────

@app.get("/api/songs")
def list_songs(status: Optional[str] = None):
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM songs WHERE status=? ORDER BY title", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM songs ORDER BY title").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/songs", status_code=201, dependencies=[Depends(require_auth)])
def create_song(song: SongIn):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO songs (title,artist,song_key,capo,tempo,time_sig,duration,status,lyrics,chords,notes)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (song.title, song.artist, song.song_key, song.capo or 0, song.tempo,
             song.time_sig or '4/4', song.duration,
             song.status, song.lyrics, song.chords, song.notes)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM songs WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)

@app.get("/api/songs/{song_id}")
def get_song(song_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Song not found")
    return dict(row)

@app.put("/api/songs/{song_id}", dependencies=[Depends(require_auth)])
def update_song(song_id: int, song: SongIn):
    with get_db() as conn:
        conn.execute(
            "UPDATE songs SET title=?,artist=?,song_key=?,capo=?,tempo=?,time_sig=?,duration=?,status=?,"
            "lyrics=?,chords=?,notes=? WHERE id=?",
            (song.title, song.artist, song.song_key, song.capo or 0, song.tempo,
             song.time_sig or '4/4', song.duration,
             song.status, song.lyrics, song.chords, song.notes, song_id)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    return dict(row)

@app.delete("/api/songs/{song_id}", dependencies=[Depends(require_auth)])
def delete_song(song_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM setlist_songs WHERE song_id=?", (song_id,))
        conn.execute("DELETE FROM songs WHERE id=?", (song_id,))
        conn.commit()
    return {"ok": True}

# ── Song file import ─────────────────────────────────────────
# Supported: .pdf (pdfplumber), .txt, .chopro, .cho, .crd, .chordpro

def _extract_pdf_text(data: bytes) -> str:
    """Extract text from a born-digital PDF using pdfplumber.
    Returns plain text with page breaks removed."""
    try:
        import pdfplumber
    except ImportError:
        raise HTTPException(
            400,
            "PDF import needs the optional 'pdfplumber' package, which isn't "
            "installed. Install it with: ./venv/bin/pip install pdfplumber  "
            "(or use a .txt / .chopro / .cho / .chordpro file instead)."
        )
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2, y_tolerance=3)
                if text:
                    pages.append(text.strip())
            return "\n\n".join(pages)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Could not extract text from PDF: {exc}")

def _guess_title_artist(text: str, filename: str) -> tuple[str, str]:
    """Heuristically extract title and artist from the first few lines."""
    lines = [l.strip() for l in text.splitlines() if l.strip()][:6]
    title = ""
    artist = ""
    for line in lines:
        # Skip lines that look like chords, keys, capo, tempo
        if re.match(r'^[A-G][#b]?', line) and len(line) < 12:
            continue
        if re.match(r'^(key|capo|tempo|bpm|tuning|time)[:\s]', line, re.I):
            continue
        if not title:
            title = line[:80]
        elif not artist:
            # Second substantive line is often the artist
            # but skip if it looks like a lyric (contains many spaces or is long)
            if len(line) < 50 and line.count(' ') < 6:
                artist = line[:80]
            break
    if not title:
        # Fall back to filename without extension
        title = re.sub(r'\.[^.]+$', '', filename).replace('_', ' ').replace('-', ' ').strip()
    return title, artist

def _normalize_newlines(text: str) -> str:
    """Collapse CR, CRLF, and stray CR-runs (e.g. the \\r\\r\\n seen in some
    exported .chopro files) into a single \\n so each source line becomes
    exactly one line. Without this, \\r\\r\\n turns every lyric line into a
    line plus a blank line, double-spacing the whole chart."""
    return re.sub(r'\r+\n?', '\n', text)


_CHORDPRO_META_MAP = {
    't': 'title', 'title': 'title', 'st': 'subtitle', 'subtitle': 'subtitle',
    'artist': 'artist', 'composer': 'composer', 'album': 'album', 'year': 'year',
    'key': 'key', 'time': 'time', 'tempo': 'tempo', 'capo': 'capo',
    'duration': 'duration',
}


def _extract_chordpro_meta(text: str):
    """Pull standard ChordPro metadata directives ({title}, {key}, {tempo}, …)
    out of the text. Returns (meta, body) where body has those metadata lines
    removed; section ({start_of_…}) and comment directives are left in place."""
    meta: dict = {}
    body: list = []
    dir_re = re.compile(r'^\{\s*([a-zA-Z_]+)\s*:\s*(.*?)\s*\}$')
    for line in text.split('\n'):
        m = dir_re.match(line.strip())
        if m:
            field = _CHORDPRO_META_MAP.get(m.group(1).lower())
            if field:
                meta.setdefault(field, m.group(2).strip())
                continue
        body.append(line)
    return meta, '\n'.join(body).strip()


_TS_OPTIONS = {'4/4', '3/4', '2/4', '5/4', '6/8', '12/8'}


def _meta_to_fields(meta: dict):
    """Map extracted ChordPro metadata to song columns:
    (song_key, capo, tempo, time_sig, duration)."""
    def _int(v):
        try:
            n = int(re.sub(r'[^\d]', '', str(v)))
            return n
        except (ValueError, TypeError):
            return None
    key = (meta.get('key') or '').strip() or None
    tempo = _int(meta.get('tempo')) if meta.get('tempo') else None
    capo = (_int(meta.get('capo')) or 0) if meta.get('capo') else 0
    ts = (meta.get('time') or '').strip()
    time_sig = ts if ts in _TS_OPTIONS else '4/4'
    duration = None
    dur = (meta.get('duration') or '').strip()
    if dur:
        if ':' in dur:
            try:
                mm, ss = dur.split(':')[:2]
                duration = int(mm) * 60 + int(ss)
            except ValueError:
                duration = None
        else:
            duration = _int(dur)
    return key, capo, tempo, time_sig, duration


def _looks_like_chordpro(text: str) -> bool:
    """True if the text has inline [chords] or {directives}."""
    return bool(re.search(r'\[[A-G][^\]]*\]', text)) or \
        bool(re.search(r'^\{\s*[a-zA-Z_]+\s*:', text, re.M))


def _import_title_artist(raw: str, filename: str, meta: dict):
    """Pick title/artist for an imported song. For ChordPro files, trust the
    {title}/{artist} directives and never scrape body lines (a lyric line is
    not an artist). For plain text, fall back to the line heuristic."""
    if _looks_like_chordpro(raw):
        title = meta.get('title') or re.sub(r'\.[^.]+$', '', filename).replace('_', ' ').replace('-', ' ').strip()
        artist = meta.get('artist') or meta.get('subtitle') or ''
        return title, artist
    return _guess_title_artist(raw, filename)


def _clean_extracted_text(text: str) -> str:
    """Normalise whitespace and remove common PDF artefacts."""
    # Collapse runs of blank lines to a single blank line
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove trailing whitespace on each line
    text = '\n'.join(l.rstrip() for l in text.splitlines())
    return text.strip()

@app.post("/api/songs/import-file", dependencies=[Depends(require_auth)])
async def import_song_file(file: UploadFile = File(...)):
    """Accept a PDF, .txt, .chopro, .cho, .crd, or .chordpro file.
    Returns extracted title, artist, and raw text ready for the song editor."""
    name = (file.filename or "").lower()
    data = await file.read()

    if name.endswith(".pdf"):
        raw = _extract_pdf_text(data)
    elif name.endswith((".txt", ".chopro", ".cho", ".crd", ".chordpro", ".pro")):
        try:
            raw = data.decode("utf-8")
        except UnicodeDecodeError:
            raw = data.decode("latin-1", errors="replace")
    else:
        raise HTTPException(400, "Unsupported file type. Accepted: .pdf .txt .chopro .cho .crd .chordpro")

    raw = _normalize_newlines(raw)
    raw = _clean_extracted_text(raw)
    meta, _body = _extract_chordpro_meta(raw)
    title, artist = _import_title_artist(raw, file.filename or "Imported Song", meta)

    # Detect whether text already looks like ChordPro (has [Chord] markers)
    is_chordpro = bool(re.search(r'\[[A-G][^\]]*\]', raw))

    return {
        "title":      title,
        "artist":     artist,
        "raw":        raw,
        "is_chordpro": is_chordpro,
        "filename":   file.filename,
    }


def _process_one_file(filename: str, data: bytes) -> dict:
    """Extract text and metadata from a single file. Returns a result dict."""
    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            raw = _extract_pdf_text(data)
        elif name.endswith((".txt", ".chopro", ".cho", ".crd", ".chordpro", ".pro", ".onsong")):
            try:
                raw = data.decode("utf-8")
            except UnicodeDecodeError:
                raw = data.decode("latin-1", errors="replace")
        else:
            return {"filename": filename, "ok": False, "error": "Unsupported file type"}

        raw = _normalize_newlines(raw)
        raw = _clean_extracted_text(raw)
        if not raw.strip():
            return {"filename": filename, "ok": False, "error": "No text content found"}

        meta, body = _extract_chordpro_meta(raw)
        title, artist = _import_title_artist(raw, filename, meta)
        is_chordpro = bool(re.search(r'\[[A-G][^\]]*\]', raw))

        # Compute confidence signals so the UI can flag results that likely
        # need manual review after import (title guessed, no key, no chords).
        title_from_directive = bool(meta.get("title"))
        has_key    = bool(meta.get("key"))
        has_chords = is_chordpro
        review_reasons = []
        if not title_from_directive: review_reasons.append("title guessed from filename")
        if not has_key:              review_reasons.append("no key detected")
        if not has_chords:           review_reasons.append("no chord content found")
        needs_review = bool(review_reasons)

        return {
            "filename":      filename,
            "ok":            True,
            "title":         title,
            "artist":        artist,
            "raw":           body if is_chordpro else raw,
            "meta":          meta,
            "is_chordpro":   is_chordpro,
            "needs_review":  needs_review,
            "review_reasons": review_reasons,
        }
    except Exception as exc:
        return {"filename": filename, "ok": False, "error": str(exc)}


@app.post("/api/songs/import-batch", dependencies=[Depends(require_auth)])
async def import_songs_batch(file: UploadFile = File(...)):
    """Accept a .zip file containing song files and bulk-import them.
    Each supported file becomes a song. Returns a summary of results."""
    import zipfile

    name = (file.filename or "").lower()
    data = await file.read()

    # Also accept a single non-zip file as a 1-item batch
    if not name.endswith(".zip"):
        result = _process_one_file(file.filename or "import", data)
        if not result["ok"]:
            raise HTTPException(400, result["error"])
        # Write single song to DB
        with get_db() as conn:
            dest = "chords" if result["is_chordpro"] else "lyrics"
            _k, _capo, _tempo, _ts, _dur = _meta_to_fields(result.get("meta") or {})
            cur = conn.execute(
                "INSERT INTO songs (title,artist,song_key,capo,tempo,time_sig,duration,status,lyrics,chords,notes)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (result["title"], result["artist"] or None, _k, _capo, _tempo, _ts, _dur,
                 "active",
                 None if dest == "chords" else result["raw"],
                 result["raw"] if dest == "chords" else None,
                 None)
            )
            conn.commit()
            song_id = cur.lastrowid
        return {"imported": 1, "skipped": 0, "results": [{
            "filename": result["filename"],
            "ok": True,
            "title": result["title"],
            "artist": result["artist"],
            "song_id": song_id,
            "needs_review": result.get("needs_review", False),
            "review_reasons": result.get("review_reasons", []),
        }]}

    # Process zip
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(400, "File is not a valid zip archive")
    with zf:

        SUPPORTED = (".pdf", ".txt", ".chopro", ".cho", ".crd", ".chordpro", ".pro", ".onsong")
        entries = [
            n for n in zf.namelist()
            if not n.startswith("__MACOSX")          # skip macOS metadata
            and not os.path.basename(n).startswith(".")  # skip hidden files
            and n.lower().endswith(SUPPORTED)
        ]

        if not entries:
            raise HTTPException(400, "Zip contains no supported song files (.chopro .cho .crd .txt .pdf .onsong)")

        with get_db() as conn:
            results = []
            imported = 0
            skipped = 0

            for entry in entries:
                basename = os.path.basename(entry)
                file_data = zf.read(entry)
                result = _process_one_file(basename, file_data)

                if not result["ok"]:
                    results.append({"filename": basename, "ok": False, "error": result["error"]})
                    skipped += 1
                    continue

                # Skip duplicates — same title already in library
                existing = conn.execute(
                    "SELECT id FROM songs WHERE LOWER(title)=LOWER(?)", (result["title"],)
                ).fetchone()
                if existing:
                    results.append({
                        "filename": basename, "ok": False,
                        "error": f"Skipped — song titled '{result['title']}' already exists",
                        "duplicate": True,
                    })
                    skipped += 1
                    continue

                dest = "chords" if result["is_chordpro"] else "lyrics"
                _k, _capo, _tempo, _ts, _dur = _meta_to_fields(result.get("meta") or {})
                try:
                    cur = conn.execute(
                        "INSERT INTO songs (title,artist,song_key,capo,tempo,time_sig,duration,status,lyrics,chords,notes)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (result["title"], result["artist"] or None, _k, _capo, _tempo, _ts, _dur,
                         "active",
                         None if dest == "chords" else result["raw"],
                         result["raw"] if dest == "chords" else None,
                         None)
                    )
                    conn.commit()
                    results.append({
                        "filename":       basename,
                        "ok":             True,
                        "title":          result["title"],
                        "artist":         result["artist"],
                        "song_id":        cur.lastrowid,
                        "needs_review":   result.get("needs_review", False),
                        "review_reasons": result.get("review_reasons", []),
                    })
                    imported += 1
                except Exception as exc:
                    results.append({"filename": basename, "ok": False, "error": str(exc)})
                    skipped += 1

        return {"imported": imported, "skipped": skipped, "results": results}

# ── Setlists ──────────────────────────────────────────────────

@app.get("/api/setlists")
def list_setlists():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM setlists ORDER BY position ASC, created_at DESC").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/setlists", status_code=201, dependencies=[Depends(require_auth)])
def create_setlist(sl: SetlistIn):
    with get_db() as conn:
        max_pos = conn.execute("SELECT COALESCE(MAX(position),0) FROM setlists").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO setlists (name,description,active,position) VALUES (?,?,1,?)",
            (sl.name, sl.description, max_pos + 1)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM setlists WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)

@app.put("/api/setlists/reorder", dependencies=[Depends(require_auth)])
def reorder_setlists(body: SetlistReorderIn):
    with get_db() as conn:
        for i, sl_id in enumerate(body.order):
            conn.execute("UPDATE setlists SET position=? WHERE id=?", (i, sl_id))
        conn.commit()
    return {"ok": True}

@app.put("/api/setlists/{sl_id}", dependencies=[Depends(require_auth)])
def update_setlist(sl_id: int, sl: SetlistIn):
    with get_db() as conn:
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
    return dict(row)

@app.delete("/api/setlists/{sl_id}", dependencies=[Depends(require_auth)])
def delete_setlist(sl_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM setlist_songs WHERE setlist_id=?", (sl_id,))
        conn.execute("DELETE FROM setlists WHERE id=?", (sl_id,))
        conn.commit()
    return {"ok": True}

@app.post("/api/setlists/{sl_id}/clone", status_code=201, dependencies=[Depends(require_auth)])
def clone_setlist(sl_id: int):
    with get_db() as conn:
        original = conn.execute("SELECT * FROM setlists WHERE id=?", (sl_id,)).fetchone()
        if not original:
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
    return dict(row)

@app.get("/api/setlists/{sl_id}/songs")
def get_setlist_songs(sl_id: int):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT ss.id as ss_id, ss.position, ss.section_label, s.*
            FROM setlist_songs ss
            JOIN songs s ON ss.song_id = s.id
            WHERE ss.setlist_id = ?
            ORDER BY ss.position
        """, (sl_id,)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/setlists/{sl_id}/songs", status_code=201, dependencies=[Depends(require_auth)])
def add_song_to_setlist(sl_id: int, entry: SetlistSongIn):
    with get_db() as conn:
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
    return {"ok": True}

@app.put("/api/setlists/{sl_id}/reorder", dependencies=[Depends(require_auth)])
def reorder_songs(sl_id: int, body: ReorderIn):
    with get_db() as conn:
        for i, ss_id in enumerate(body.order):
            conn.execute(
                "UPDATE setlist_songs SET position=? WHERE id=? AND setlist_id=?",
                (i, ss_id, sl_id)
            )
        conn.commit()
    return {"ok": True}

@app.delete("/api/setlists/{sl_id}/songs/{ss_id}", dependencies=[Depends(require_auth)])
def remove_from_setlist(sl_id: int, ss_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM setlist_songs WHERE id=? AND setlist_id=?", (ss_id, sl_id))
        conn.commit()
    return {"ok": True}

@app.put("/api/setlists/{sl_id}/songs/{ss_id}/section", dependencies=[Depends(require_auth)])
def set_section_label(sl_id: int, ss_id: int, body: dict):
    with get_db() as conn:
        conn.execute(
            "UPDATE setlist_songs SET section_label=? WHERE id=? AND setlist_id=?",
            (body.get("label"), ss_id, sl_id)
        )
        conn.commit()
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
    with get_db() as conn:
        row = conn.execute("SELECT * FROM songs WHERE id=?", (body.song_id,)).fetchone()
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
    with get_db() as conn:
        row = conn.execute("SELECT * FROM songs WHERE id=?", (body.song_id,)).fetchone()
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
# metro_state: persisted so Pi restart mid-show restores metronome
metro_state = _load_state("metro_state", {
    "on":            False,
    "bpm":           None,
    "beats_per_bar": 4,
    "server_epoch":  None,
})

# monitor_config: persisted so Pi restart restores monitor display prefs
def _default_monitor_config():
    return {
        "name":      "Unnamed Monitor",
        "mode":      "chords",
        "cols":      False,
        "fit":       False,
        "hc":        False,
        "portrait":  False,
        "rotated":   False,
        "rotation":  0,
        "usecapo":   True,
        "fontscale": 1.0,
        "last_seen": None,
    }

# monitor_configs: {monitor_id: config_dict}. Each physical monitor/kiosk
# browser gets its own persistent id (generated client-side, stored in that
# browser's localStorage) and its own independent settings — so a "Stage
# Left" monitor can run a different capo/layout/mode than a "Stage Right"
# one. Persisted so a Pi restart restores every monitor's display prefs.
monitor_configs = _load_state("monitor_configs", {})
if not monitor_configs:
    # One-time migration: older builds had a single global "monitor_config".
    # Carry it forward as the first monitor's config rather than losing it.
    _legacy = _load_state("monitor_config", {})
    if _legacy:
        _migrated = _default_monitor_config()
        _migrated.update({k: v for k, v in _legacy.items() if k in _migrated})
        _migrated["name"] = "Monitor"
        monitor_configs[str(uuid.uuid4())] = _migrated
        _save_state("monitor_configs", monitor_configs)

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    import time, json
    await manager.connect(websocket)
    await websocket.send_json({"type": "live_update", **live_state})
    # Send current rehearsal state to newly connected client
    if rehearsal_state["active"] and rehearsal_state["song"]:
        await websocket.send_json({"type": "rehearsal_update", "song": rehearsal_state["song"]})
    # Metro state is not sent on reconnect — count-in is a one-shot action
    # triggered explicitly by the leader, not a persistent state to restore.
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
                        metro_state.update({
                            "on":            True,
                            "bpm":           msg["bpm"],
                            "beats_per_bar": msg.get("beats_per_bar", 4),
                            "server_epoch":  msg.get("server_epoch", time.time() * 1000),
                        })
                        _save_state("metro_state", metro_state)
                        # Broadcast to all — monitor will flash, others ignore
                        await manager.broadcast({
                            "type":         "metronome_start",
                            "bpm":          metro_state["bpm"],
                            "beats_per_bar": metro_state["beats_per_bar"],
                            "server_epoch": metro_state["server_epoch"],
                        })
                    elif msg.get("type") == "metronome_stop":
                        metro_state["on"] = False
                        metro_state["server_epoch"] = None
                        _save_state("metro_state", metro_state)
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
                    elif msg.get("type") == "standby_logo_update":
                        await manager.broadcast({"type": "standby_logo_update"})
                    elif msg.get("type") == "monitor_identify":
                        # A monitor announcing its persistent id on connect.
                        # Register the id→connection mapping and send back
                        # that monitor's own config (creating a default
                        # entry the first time this id is ever seen).
                        mid = str(msg.get("monitor_id") or "").strip()[:64]
                        if mid:
                            manager.set_monitor_id(websocket, mid)
                            if mid not in monitor_configs:
                                monitor_configs[mid] = _default_monitor_config()
                            monitor_configs[mid]["last_seen"] = time.time()
                            _save_state("monitor_configs", monitor_configs)
                            await websocket.send_json({
                                "type": "monitor_config",
                                "monitor_id": mid,
                                **monitor_configs[mid],
                            })
                    elif msg.get("type") == "monitor_config":
                        # Config push targeted at one specific monitor (from
                        # /monitor/setup or the leader's monitor panel).
                        mid = str(msg.get("monitor_id") or "").strip()[:64]
                        if not mid:
                            continue
                        cfg = monitor_configs.get(mid) or _default_monitor_config()
                        # Rotation: accept new `rotation` (0/90/-90) or legacy
                        # `rotated` boolean; keep both fields in sync.
                        if "rotation" in msg:
                            try:
                                _rot = int(msg.get("rotation") or 0)
                            except (TypeError, ValueError):
                                _rot = 0
                        elif "rotated" in msg:
                            _rot = 90 if msg.get("rotated") else 0
                        else:
                            _rot = cfg.get("rotation", 0)
                        cfg.update({
                            "name":      str(msg.get("name", cfg["name"]))[:60] or cfg["name"],
                            "mode":      msg.get("mode",      cfg["mode"]),
                            "cols":      bool(msg.get("cols",      cfg["cols"])),
                            "fit":       bool(msg.get("fit",       cfg["fit"])),
                            "hc":        bool(msg.get("hc",        cfg["hc"])),
                            "portrait":  bool(msg.get("portrait",  cfg["portrait"])),
                            "rotation":  _rot,
                            "rotated":   _rot != 0,
                            "usecapo":   bool(msg.get("usecapo",   cfg["usecapo"])),
                            "fontscale": float(msg.get("fontscale", cfg["fontscale"])),
                        })
                        monitor_configs[mid] = cfg
                        _save_state("monitor_configs", monitor_configs)
                        await manager.send_to_monitor(mid, {
                            "type": "monitor_config",
                            "monitor_id": mid,
                            **cfg,
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
    html = re.sub(r'/static/leader\.css(\?v=[^"]*)?', f'/static/leader.css?v={BUILD_ID}', html)
    # Inject a meta tag so the SW and JS can read the build ID
    meta = f'<meta charset="UTF-8">\n<meta name="build-id" content="{BUILD_ID}">'
    html = html.replace('<meta charset="UTF-8">', meta)
    return html

@app.get("/monitor/setup")
def monitor_setup():
    r = FileResponse("static/monitor-setup.html")
    r.headers["Cache-Control"] = "no-store"
    return r

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


def _get_lan_ip() -> str:
    """Best-effort LAN-facing IP address of this machine. Used so the
    monitor's standby screen can show a setup URL that's reachable from
    another device on the network — `location.origin` alone isn't enough,
    since a local kiosk browser opens the page via http://localhost, which
    means nothing to someone else's phone."""
    try:
        # Doesn't actually send any data; just asks the OS which local
        # interface/IP it would use to reach an external address. This is
        # the standard portable trick for getting the real LAN IP without
        # parsing `hostname -I` (which can return multiple/irrelevant
        # addresses on a multi-interface machine).
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


@app.get("/api/server-info")
def get_server_info(request: Request):
    """LAN IP and port this server is reachable on, for building URLs that
    work from other devices (e.g. the monitor's on-screen setup link).
    Port is read from the request itself (the Host header) rather than
    assumed, since the app has no fixed/known port — it's whatever was
    passed to `uvicorn --port` at launch."""
    host_header = request.headers.get("host", "")
    port = 8000
    if ":" in host_header:
        try:
            port = int(host_header.rsplit(":", 1)[1])
        except ValueError:
            pass
    return {"ip": _get_lan_ip(), "port": port}


@app.get("/api/monitors")
def list_monitors():
    """All monitors that have ever identified themselves, most recently
    active first, with name/connected/last_seen so stale entries are
    identifiable and safe to remove."""
    items = [
        {
            "id":        mid,
            "name":      cfg.get("name", "Unnamed Monitor"),
            "connected": manager.monitor_connected(mid),
            "last_seen": cfg.get("last_seen"),
        }
        for mid, cfg in monitor_configs.items()
    ]
    items.sort(key=lambda m: (not m["connected"], -(m["last_seen"] or 0)))
    return items


@app.delete("/api/monitors/{monitor_id}", dependencies=[Depends(require_auth)])
def delete_monitor(monitor_id: str):
    """Forget a monitor — e.g. one whose browser storage was cleared or
    device was replaced, leaving an orphaned entry. Does not affect a
    live connection; it just won't be remembered/configurable anymore."""
    if monitor_id not in monitor_configs:
        raise HTTPException(404, "Unknown monitor id")
    del monitor_configs[monitor_id]
    _save_state("monitor_configs", monitor_configs)
    return {"ok": True}


@app.get("/api/monitors/{monitor_id}/config")
def get_monitor_config(monitor_id: str):
    """A specific monitor's current config, for populating the setup page
    or leader panel without waiting on a WebSocket round-trip."""
    cfg = monitor_configs.get(monitor_id)
    if cfg is None:
        raise HTTPException(404, "Unknown monitor id")
    return {"monitor_id": monitor_id, **cfg}

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


@app.get("/api/standby-logo")
def get_standby_logo():
    """Return the current custom standby logo filename, or null if none set."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM app_state WHERE key='standby_logo'"
        ).fetchone()
    if row and os.path.exists(os.path.join("static/img", row[0])):
        return {"filename": row[0]}
    return {"filename": None}

@app.post("/api/standby-logo", dependencies=[Depends(require_auth)])
async def upload_standby_logo(file: UploadFile = File(...)):
    """Upload a custom standby logo. Saves to static/img/standby-logo.<ext>."""
    name = file.filename or ""
    ext  = os.path.splitext(name)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        raise HTTPException(400, "Unsupported image type. Use PNG, JPG, GIF, WebP, or SVG.")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image too large. Maximum size is 5 MB.")
    # Remove any previous custom logo
    _clear_standby_logo_file()
    fname = f"standby-logo{ext}"
    dest  = os.path.join("static/img", fname)
    with open(dest, "wb") as f:
        f.write(data)
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_state (key, value) VALUES ('standby_logo', ?)",
            (fname,)
        )
        conn.commit()
    return {"filename": fname}

@app.delete("/api/standby-logo", dependencies=[Depends(require_auth)])
def delete_standby_logo():
    """Remove the custom standby logo and revert to default."""
    _clear_standby_logo_file()
    with get_db() as conn:
        conn.execute("DELETE FROM app_state WHERE key='standby_logo'")
        conn.commit()
    return {"ok": True}

def _clear_standby_logo_file():
    """Delete any existing standby-logo.* file from disk."""
    img_dir = "static/img"
    for fname in os.listdir(img_dir):
        if fname.startswith("standby-logo."):
            try:
                os.remove(os.path.join(img_dir, fname))
            except OSError:
                pass

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

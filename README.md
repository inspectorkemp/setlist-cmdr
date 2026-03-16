# 🎸 Setlist CMDR

A full-featured setlist and song management system that runs entirely locally — on your **PC for development and testing**, then move it to a **Raspberry Pi** for gigs. No internet required. Musicians connect their tablets to the same WiFi and open a browser.

---

## What's included

| Feature | Details |
|---|---|
| Song library | Title, artist, key, tempo, duration, status, lyrics, chords, notes |
| ChordPro chords | Inline chord annotations `[C]Word [G]Word` with auto-transpose |
| Setlist builder | Multiple setlists, drag songs in, up/down reorder, section labels |
| Real-time sync | WebSocket push — all tablets update instantly when leader changes song |
| Per-musician view | Each tablet independently picks Lyrics or Chords mode |
| Autoscroll | Smooth scrollable lyrics during performance |
| Transpose | Each musician can independently shift chords ±11 semitones |
| Synced flash metronome | Server-anchored beat clock — all devices flash in phase |
| Live stage control | Leader picks current song; "Next" song preview on all screens |
| Musician count | Leader sees how many devices are connected |
| Offline / local | Runs on Pi's own WiFi hotspot — no router, no internet needed |

---

## Running on your PC (development & testing)

The quickest way to get started. Works on **Windows, macOS, and Linux**.

### Requirements
- Python 3.9+ installed and on your PATH
- Any modern browser

### Start it

**Windows** — double-click `start.bat`, or in a terminal:
```
python run.py
```

**macOS / Linux:**
```bash
python3 run.py
```

That's it. `run.py` will:
1. Create a Python virtual environment (first run only)
2. Install dependencies automatically
3. Start the server
4. Open the leader view in your browser

### Useful options
```bash
python run.py --port 8080        # use a different port
python run.py --no-browser       # don't auto-open the browser
python run.py --no-reload        # disable auto-restart on code changes
```

### Testing with multiple "musicians"
Open extra browser tabs or windows pointing at `http://localhost:8000/` to simulate musician devices. Each tab acts as an independent musician (enter a different name in each).

### Your data
The database (`setlist.db`) is created in the same folder on first run. Everything you add during PC testing — songs, setlists — will be there when you copy the folder to the Pi.

---

## Deploying to Raspberry Pi

Once you're happy with the setup on your PC:

### Requirements

- Raspberry Pi 3B+ or newer (Pi 4 recommended)
- Raspberry Pi OS (Bullseye or Bookworm)
- Python 3.9+
- Any tablet or phone with a browser (Chrome/Firefox on Android, Safari on iPad)

### Pi setup (first time)

```bash
# Copy the setlist-cmdr folder to your Pi (USB, scp, etc.)
cd setlist-cmdr
bash setup.sh
```

The setup script creates a virtual environment, installs dependencies, and registers a systemd service so Setlist CMDR starts automatically on boot.

---

## WiFi Hotspot (gig mode — no router needed)

```bash
bash setup-hotspot.sh
```

This makes the Pi broadcast its own WiFi network:
- **Network name:** `SetlistCMDR`
- **Password:** `rockandroll`
- **Leader:** `http://192.168.50.1:8000/leader`
- **Musicians:** `http://192.168.50.1:8000/`

> You can change the SSID and password by editing the variables at the top of `setup-hotspot.sh`.

---

## How to use it

### Band leader (1 device — usually laptop or the leader's tablet)
1. Open `http://<pi-ip>:8000/leader`
2. **Songs tab** — add your whole repertoire. Paste lyrics and/or ChordPro chords.
3. **Setlists tab** — create a setlist, add songs, reorder with ↑/↓, add section labels.
4. **Live Control tab** — pick a setlist, hit **GO LIVE**. Navigate songs with Prev/Next or click any song in the queue.

### Musicians (each person's tablet)
1. Connect tablet to the Pi's WiFi (`SetlistCMDR`)
2. Open browser → `http://192.168.50.1:8000/`
3. Enter your name and tap **JOIN**
4. Your screen will automatically update when the leader changes the current song
5. Toggle **LYRICS / CHORDS** — your preference is saved
6. Use **♭ / ♯** to transpose independently
7. Tap **⏩ AUTO** to start autoscrolling

---

## ChordPro format (for chords)

Inline format: wrap chord names in square brackets before the syllable they're played on.

```
[G]Here comes the [Em]sun, [C]doo-doo-doo-[D]doo
[G]Here comes the [Em]sun, and I [C]say it's all-[D]right
```

Musicians who choose **Chords** view see the chords highlighted inline.
Musicians who choose **Lyrics** view see the text with all chord markers stripped.

---

## Song status values

| Status | Meaning |
|---|---|
| `Active` | Ready to perform |
| `Needs work` | Still learning / not gig-ready |
| `Maybe` | Possible addition |
| `Retired` | Dropped from repertoire |

---

## Data

All data is stored in `setlist.db` (SQLite) in the same folder as `main.py`. Back this file up regularly — it contains everything.

```bash
# Backup
cp setlist.db band-$(date +%Y%m%d).db
```

---

## Service management

```bash
sudo systemctl status  setlist-cmdr   # check status
sudo systemctl restart setlist-cmdr   # restart after changes
sudo systemctl stop    setlist-cmdr   # stop
sudo journalctl -u     setlist-cmdr -f  # live logs
```

---

## File structure

```
setlist-cmdr/
├── main.py              ← FastAPI server (all API endpoints + WebSocket)
├── setlist.db              ← SQLite database (auto-created on first run)
├── requirements.txt     ← Python dependencies
├── setup.sh             ← First-time setup script
├── setup-hotspot.sh     ← Optional WiFi hotspot config
├── venv/                ← Python virtual environment (created by setup.sh)
└── static/
    ├── musician.html    ← Tablet stage view  ( http://pi:8000/ )
    └── leader.html      ← Leader management  ( http://pi:8000/leader )
```

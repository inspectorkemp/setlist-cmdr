<div align="center">
<img src="static/img/logo_large.png" alt="Setlist CMDR" width="380">
</div>

# Setlist CMDR

A full-featured setlist and song management system that runs entirely on your local network. No internet required. Run it on your PC for testing and development, then deploy to a Raspberry Pi for gigs. Musicians connect their tablets or phones to the same WiFi and open a browser. Nothing to install on their devices.

---

## Features

**Song library**
Full CRUD management for your entire repertoire. Each song stores title, artist, key, tempo, duration, status, lyrics, chords (ChordPro format), and notes. Filter by status and search by title or artist. Import songs in bulk via CSV with a column mapper and row preview. Four status levels: Active, Needs Work, Maybe, Retired.
<div align="center">
<img width="1094" height="439" alt="image" src="https://github.com/user-attachments/assets/13cda29e-0bc3-405c-86f4-096c6e599baf" />
</div>

**Setlists**
Create multiple setlists. Add songs from your library, drag to reorder, add section labels between songs, and see a running total duration. Rename by clicking the title or the edit button. Clone any setlist to use it as a starting point for a new one. Mark setlists as Active or Inactive. Inactive setlists are hidden from the Live Control dropdown so they cannot be accidentally deployed. The setlist list itself can be reordered by dragging.
<div align="center">
<img width="1083" height="518" alt="image" src="https://github.com/user-attachments/assets/321848bb-be63-441f-9a3d-4e39fc911253" />
</div>

**Live Control**
Select an active setlist and hit Deploy. All connected musician screens update instantly via WebSocket. Navigate with Prev and Next buttons, or click any song in the queue to jump directly to it. Each musician sees the current song title, key, tempo, and a next-song ribbon so they can prepare. End the show with Stand Down and all musician screens return to standby.

**Synced flash metronome**
The band leader starts the metronome and all connected devices flash in phase. Sync is achieved through an NTP-style clock calibration over WebSocket: each device exchanges 10 round-trip timestamps with the server on connect, discards the noisiest half, and averages the rest to compute a precise clock offset. The leader broadcasts a single start message containing the BPM and an absolute epoch timestamp. Every device computes its own beat schedule from that shared epoch, so drift cannot accumulate regardless of network jitter or timer imprecision. Expected sync accuracy on a local Pi hotspot is under 10ms. The flash uses a radial amber overlay with a brighter accent on beat 1. Auto-stops after a configurable timeout of 10, 15, 20, or 30 seconds.

**Signal messages**
Send instant one-tap text alerts to all musician screens during a live show. Eight configurable slots are mapped to F1-F8 keyboard hotkeys. Default signals: RUSHING, DRAGGING, CHORUS, BRIDGE, KEEP GOING, WRAP IT UP, HOLD HERE, EYES ON ME. Labels are fully editable and saved per device. A large amber banner slides down on every musician screen and auto-dismisses after 3 seconds.

**Per-musician controls**
Each musician independently toggles between Lyrics and Chords view with the preference saved on device. Transpose chords up or down by up to 11 semitones without affecting anyone else. Toggle autoscroll to drift through lyrics at reading pace.

**ChordPro chords**
Chord annotations sit inline with lyrics using square bracket notation. Transpose is applied client-side in real time.

**Musician roster**
The leader sees a live count of connected musicians in the nav bar. Clicking the count opens a popup listing each musician by name. The roster updates in real time as people join or leave.

**Database backup and restore**
Download the live SQLite database directly from the leader browser with one click. The file is timestamped automatically. Upload a previously saved backup to restore it. The server validates the file is a real SQLite database with the correct schema before replacing anything, and saves an automatic backup of the current database first.

**iPad and Desktop modes**
A toggle in the nav bar switches between iPad mode and Desktop mode. iPad mode uses larger tap targets, bigger fonts, and press feedback instead of hover states. Desktop mode is compact and mouse-optimized. The selected mode is saved per device and defaults to iPad.

**Progressive Web App**
Both the leader and musician pages can be installed to the home screen on iPad, iPhone, and Android. Once installed, the app launches full-screen with no browser chrome. The interface shell loads from the device cache instantly, even before the Pi's WiFi hotspot is fully up.
<div align="center">
<img width="1095" height="1300" alt="image" src="https://github.com/user-attachments/assets/5536d5bd-d60c-4e90-8819-3ce6468875b5" />
</div>
---

## Running on your PC

Works on Windows, macOS, and Linux. Requires Python 3.9 or newer.

**Windows:** double-click `start.bat`, or from a terminal:
```
python run.py
```

**macOS and Linux:**
```bash
python3 run.py
```

On first run, `run.py` creates a virtual environment, installs all dependencies, starts the server, and opens the leader view in your browser. Subsequent runs skip the install step.

**Options:**
```bash
python run.py --port 8080     # use a different port
python run.py --no-browser    # skip auto-opening the browser
```

**Testing with multiple musicians:** open additional browser tabs pointing at `http://localhost:8000/` and enter a different name in each. Each tab acts as an independent musician screen.

The database (`setlist.db`) is created in the project folder on first run. Songs and setlists you add during PC testing will carry over when you copy the folder to the Pi.

---

## Deploying to Raspberry Pi

**Supported hardware:**
- Raspberry Pi 3B+ or newer recommended
- Pi Zero 2W will work but is not ideal for hotspot use at a gig
- Pi Zero W is not recommended

**Requirements:**
- Raspberry Pi OS 64-bit (Bookworm recommended)
- Python 3.9 or newer

**First-time setup:**
```bash
cd setlist-cmdr
bash setup.sh
```

This creates the virtual environment, installs dependencies, and registers a systemd service so Setlist CMDR starts automatically on every boot.

---

## WiFi Hotspot (gig mode)

To run without any external router, configure the Pi to broadcast its own WiFi network:

```bash
bash setup-hotspot.sh
```

Default network settings:
- Network name: `SetlistCMDR`
- Password: `rockandroll`
- Leader URL: `http://192.168.50.1:8000/leader`
- Musician URL: `http://192.168.50.1:8000/`

Edit the variables at the top of `setup-hotspot.sh` to change the SSID or password before running it.

---

## Installing as a PWA (home screen app)

**iPad or iPhone (Safari only):**
1. Connect to the Pi's WiFi and open the correct URL in Safari
2. Tap the Share button (the box with an arrow pointing up)
3. Tap "Add to Home Screen"
4. Tap Add

**Android (Chrome):**
1. Open the URL in Chrome
2. Tap the three-dot menu
3. Tap "Add to Home Screen" or "Install app"

The app launches full-screen with the Setlist CMDR icon. The leader page and musician page can each be installed separately. Each person installs whichever applies to them.

---

## Band leader workflow

1. Open `http://<pi-ip>:8000/leader` in your browser or installed PWA
2. Go to the **Songs** tab and add your entire repertoire. Paste in lyrics and ChordPro chords. Set tempo and key on each song so the metronome and transpose features work correctly.
3. Go to the **Setlists** tab and create a setlist for each show or occasion. Add songs, drag to reorder, and add section labels such as Opener, Slow Set, or Closer to divide the list visually.
4. Mark setlists you are not currently using as Inactive so they do not appear in the Live Control picker.
5. Go to the **Live Control** tab before the show, select your setlist, and hit **Deploy** when you are ready to go live.
6. During the show, use **Prev** and **Next** to navigate songs, or click any song in the queue to jump directly. Use the signal bar buttons or F1-F8 keyboard shortcuts to flash messages to all musicians. Hit the Flash button to start the synced metronome on all devices.

---

## Musician workflow

1. Connect your device to the Pi's WiFi (default network name is `SetlistCMDR`)
2. Open Safari or Chrome and go to `http://192.168.50.1:8000/`
3. Enter your name and tap **JOIN**
4. The screen shows **STANDBY** until the leader deploys a show
5. Once live, your screen updates automatically every time the leader moves to a new song
6. Tap **LYRICS** or **CHORDS** to switch views (saved on your device)
7. Tap the flat or sharp buttons to transpose independently of other musicians
8. Tap **AUTO** to start autoscrolling through lyrics

---

## ChordPro format

Wrap chord names in square brackets immediately before the syllable where they are played:

```
[G]Here comes the [Em]sun, [C]doo-doo-doo-[D]doo
[G]Here comes the [Em]sun, and I [C]say it's all-[D]right
```

In Chords view, chords are highlighted inline with the lyrics. In Lyrics view, all chord markers are stripped and only the text is shown. Transpose shifts all chords up or down on that device without affecting anyone else.

---

## CSV import

Click **Import CSV** in the Songs toolbar to bulk-import songs. The column mapper lets you match any column header to the correct field. A preview table shows the first several rows before you commit. Download the template CSV for a correctly formatted starting point.

Supported fields: Title, Artist, Key, Tempo (BPM), Duration (seconds), Status, Lyrics, Chords, Notes.

---

## Song status values

| Status | Meaning |
|---|---|
| Active | Ready to perform |
| Needs Work | Still learning or not gig-ready |
| Maybe | Possible addition to repertoire |
| Retired | Dropped from active use |

---

## Database management

The database (`setlist.db`) lives in the project folder. All songs, setlists, and setlist contents are stored here.

**Download from the browser:** click the DB download button in the leader nav bar. The file downloads with a timestamp in the filename.

**Restore from the browser:** click the DB upload button in the leader nav bar and select a `.db` file. The server validates it, backs up the current database automatically, then replaces it. The page reloads with the restored data.

**Manual backup on the Pi:**
```bash
cp setlist.db setlist-$(date +%Y%m%d).db
```

---

## Service management (Pi)

```bash
sudo systemctl status  setlist-cmdr     # check status
sudo systemctl restart setlist-cmdr     # restart after changes
sudo systemctl stop    setlist-cmdr     # stop
sudo journalctl -u     setlist-cmdr -f  # live logs
```

---

## File structure

```
setlist-cmdr/
├── main.py                  FastAPI server, all API endpoints and WebSocket
├── run.py                   Cross-platform launcher, creates venv and installs deps
├── requirements.txt         Python dependencies
├── setlist.db               SQLite database, auto-created on first run
├── setup.sh                 First-time Pi setup script
├── setup-hotspot.sh         Optional WiFi hotspot configuration
├── start.bat                Windows quick-start
├── start.sh                 Linux and macOS quick-start
└── static/
    ├── leader.html          Band leader interface
    ├── leader.css           All leader styles, external file
    ├── musician.html        Musician stage view
    ├── sw.js                PWA service worker
    ├── manifest.json        PWA web app manifest
    └── img/
        ├── logo_large.png
        ├── logo_bottom_right_wide.png
        ├── logo_top_right.png
        ├── logo_bottom_left.png
        ├── icon-192.png
        ├── icon-512.png
        └── apple-touch-icon.png
```

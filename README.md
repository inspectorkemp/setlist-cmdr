<div align="center">
<img src="static/img/logo_large.png" alt="Setlist CMDR" width="380">
</div>

# Setlist CMDR

A band setlist and song management system that runs on your local network. No internet required at the venue. Run it on a Raspberry Pi, connect all devices to the same WiFi, and everyone opens a browser. Nothing to install on phones or tablets.

---

## What it does

The band leader controls everything from a PIN-protected web interface. Musicians open a separate page on their own devices and see the current song in real time. A confidence monitor page is available for a floor wedge or large display. All screens stay in sync over WebSocket with no polling or page refreshes.

---

## Features

**Song library**
Store your entire repertoire. Each song holds: title, artist, key, capo, tempo, duration, status, lyrics, chords in ChordPro format, and notes. Search by title or artist. Filter by status. Four status levels: Active, Needs Work, Maybe, Retired.

**Capo**
Capo is a first-class field. When set, chord displays show the fingered shapes rather than the sounding pitch. A song in B with Capo 2 shows G-shape chords. The per-device transpose control applies on top of the capo offset.

**ChordPro chord editor**
Chords are stored in ChordPro format with chord names in square brackets inline with lyrics. The song editor includes a fullscreen split editor with a live preview. A Convert button accepts the chords-above-lyrics format used by Ultimate Guitar and most plain-text chord sheets and converts it to ChordPro automatically.

**Section markers**
Section markers use the same bracket syntax as chords. Any token that is not a valid chord name is treated as a section marker: [Verse 1], [Chorus], [Bridge], [Pre-Chorus], [Outro], etc. Section headers render in amber with a ruled divider. A bare back-reference such as a second [Chorus] with no following content renders as a dimmed repeat cue at reduced opacity rather than duplicating the full text.

**CSV import**
Bulk-import songs from a spreadsheet. Download a template from the Songs toolbar, fill in your songs, upload the CSV, map each column to the correct field, and import. Supported fields: Title, Artist, Key, Tempo, Duration, Status. Lyrics, chords, and notes must be added per song after import.

**File import**
Import a chord sheet using the Import button in the Songs toolbar. Supported formats: .pdf, .txt, .chopro, .cho, .crd, .chordpro, .pro. The server extracts the text, auto-detects title and artist from the first lines, and opens a review modal where you can edit before creating the song. Born-digital PDFs extract cleanly. Scanned image PDFs contain no extractable text and are not supported.

**Setlists**
Create and manage multiple setlists. Add songs from your library, drag to reorder, insert section labels between songs, and see a running total duration. Clone any setlist as a starting point. Mark setlists Active or Inactive. The setlist list itself can be reordered by dragging.

**Live Control**
Select an active setlist and click Engage. All connected musician screens update instantly. Navigate with Prev and Next, or click any song in the queue to jump directly. End the show with Stand Down to return all screens to standby.

**Rehearsal mode**
Click Rehearse on any song in the Songs tab to push that song to all musician screens without starting a live show. The leader goes directly to the stage view. Musicians see a teal Rehearsal banner. End with End Rehearsal in the control bar.

**Confidence monitor**
A full-screen display page at /monitor designed for a floor wedge or large display. Shows the current song title, key, and BPM in large type, followed by the full lyrics or chords, with a Next ribbon at the bottom. Tracks the leader scroll position and transpose changes in real time.

The monitor standby screen shows a QR code linking to /monitor/setup. Scan it on your phone to configure the display without touching the TV or editing the URL. The leader can also push monitor settings remotely from the Settings modal.

Monitor settings (all available via remote push, QR setup page, or URL params):

| Setting | URL param | Effect |
|---|---|---|
| View mode | mode=chords or mode=lyrics | Which content to show (default: chords) |
| Two columns | cols=1 | Side-by-side column layout |
| Fit mode | fit=1 | Compact layout with auto-fit font scaling |
| High contrast | hc=1 | Brighter text for washed-out displays |
| Portrait (hardware) | portrait=1 | Layout adjustments for a physically rotated TV |
| Rotate 90 degrees | (remote only) | Software rotation for landscape TVs showing portrait content |
| Font scale | fontscale=1.3 | Multiply the base font size |

**Rotate 90 degrees**
Rotates the entire browser content 90 degrees clockwise using a CSS transform. Use this when the TV is in landscape mode but you want portrait content. No TV or OS settings need to change. Push this setting from the leader Settings modal or the /monitor/setup page.

**Synced flash metronome**
The leader starts the metronome and all connected devices flash in phase. Each device exchanges 16 round-trip timestamps with the server on connect, discards the 8 with the worst latency, and averages the rest to compute a clock offset. Re-syncs every 30 seconds. Uses the Web Audio API where available. Auto-stops after a configurable timeout of 10, 15, 20, or 30 seconds.

**Signal messages**
Send one-tap text alerts to all musician screens. Eight configurable slots mapped to F1 through F8. Default signals: RUSHING, DRAGGING, CHORUS, BRIDGE, KEEP GOING, WRAP IT UP, HOLD HERE, EYES ON ME. Labels are editable. A large amber banner appears on every musician screen and dismisses after 3 seconds.

**Bluetooth page turner pedal - leader**
Pair any Bluetooth page turner with the leader device and assign keys in Settings. Four assignable actions: Next Song, Prev Song, Scroll Down, Scroll Up. Three presets: Arrow keys (AirTurn, PageFlip, Donner), Page Up/Down (iRig BlueTurn), bracket keys.

**Bluetooth page turner pedal - musician**
Each musician can assign their own pedal independently via the gear button in the musician header. Four assignable actions: Scroll Down, Scroll Up, Lyrics/Chords toggle, Auto Scroll toggle. Two presets: Arrow keys, Page Up/Down. Settings are saved per device.

**Per-musician controls**
Each musician independently controls: Lyrics/Chords view toggle, font size slider, line spacing (Normal/Tight/Loose), two-column layout, high contrast mode, transpose up or down by up to 11 semitones, and autoscroll. All preferences are saved per device. The band leader has the same controls in their stage view.

**Compact stage mode**
A compact button in the leader live control bar collapses all chrome to minimum height, maximising the content area. Saved across sessions.

**Musician roster**
The leader sees a live count of connected musicians in the nav bar. Clicking it opens a popup showing each musician by name. The roster updates in real time.

**Band member roster**
The leader manages a named list of band members from the Crew modal. Names appear as tap-to-join buttons on the musician name screen. A freeform text input remains for guests.

**PIN-protected leader interface**
The leader page requires a PIN. The default PIN is 1234. Change it via Settings. Sessions last 24 hours. The musician page and monitor page are open without a PIN.

**Live state persistence**
The current setlist, song index, and live status are written to the database on every change. If the server restarts mid-show, reconnecting clients receive the current state immediately.

**Database backup and restore**
Download the live SQLite database from the leader nav bar. Upload a backup to restore. The server validates the file before replacing anything and saves a backup before overwriting. Schema migrations run automatically on startup.

**Font caching**
By default fonts load from Google Fonts. Run setup-fonts.sh once while the Pi has internet access to cache all fonts locally.

**iPad and Desktop modes**
A toggle in the nav bar switches between iPad mode (larger touch targets, bigger fonts) and Desktop mode (compact, mouse-optimised). Defaults to iPad mode. Saved per device.

**Progressive Web App**
The leader page and musician page can be installed to the home screen on iPad, iPhone, and Android. Each has its own manifest. Launches full-screen with no browser chrome.

---

## Requirements

- Python 3.9 or newer
- Works on Windows, macOS, and Linux for development
- Raspberry Pi 3B or newer for production deployment

---

## Running on your PC

**Windows:** double-click start.bat, or from a terminal:
```
python run.py
```

**macOS and Linux:**
```bash
python3 run.py
```

On first run, run.py creates a virtual environment, installs all dependencies, starts the server, and opens the leader view in your browser. Subsequent runs skip the install step.

```bash
python run.py --port 8080     # use a different port
python run.py --no-browser    # skip auto-opening the browser
```

To test with multiple musicians, open additional browser tabs at http://localhost:8000/ and enter a different name in each.

---

## Deploying to Raspberry Pi

**Setup:**
```bash
cd setlist-cmdr
bash setup.sh
```

This creates the virtual environment, installs all dependencies, and registers a systemd service that starts Setlist CMDR automatically on every boot.

**Finding the Pi IP address:**
```bash
hostname -I
```

Open the leader interface at http://pi-ip:8000/leader and the musician page at http://pi-ip:8000/.

**After deploying updated files, restart the service:**
```bash
sudo systemctl restart setlist-cmdr
```

If changes are not appearing in the monitor browser after a restart, clear cached images and files in the browser before reloading.

---

## Confidence monitor setup

Open http://pi-ip:8000/monitor on any browser connected to the same network.

**Three ways to configure the display without SSH:**

1. QR code: When no show is active, the standby screen shows a QR code. Scan it on your phone, adjust the settings, tap Apply.
2. Leader remote push: Open Settings in the leader nav bar, scroll to Confidence Monitor, adjust the toggles, click Push to Monitor.
3. Setup page: Open http://pi-ip:8000/monitor/setup in any browser on the network.

**Kiosk setup for a dedicated Pi:**

Add a file at /etc/xdg/autostart/monitor.desktop:

```
[Desktop Entry]
Type=Application
Name=Monitor
Exec=chromium-browser --kiosk --noerrdialogs --disable-infobars http://main-pi-ip:8000/monitor
```

The monitor Pi needs no server of its own. It opens a browser pointed at the main Pi.

---

## First login

The default leader PIN is 1234. After logging in, go to Settings and set a new PIN.

---

## Setting up band members

1. Click Crew in the nav bar
2. Type a name and press Enter or click Add
3. Repeat for each band member

---

## Band leader workflow

1. Open http://pi-ip:8000/leader and log in
2. Go to Songs and build your library. Set tempo and key for metronome and transpose to work correctly.
3. Go to Setlists and create a setlist. Add songs, drag to reorder, add section labels.
4. Mark setlists you are not using as Inactive.
5. Go to Live Control, select your setlist, and click Engage.
6. Use Prev and Next to navigate, or click any song in the queue.
7. Use the signal bar or F1 through F8 to send messages to musicians.

---

## Rehearsal workflow

1. Go to Songs
2. Click Rehearse on any song
3. All musician screens show the song with a teal Rehearsal banner
4. Click End Rehearsal in the control bar when done

---

## Musician workflow

1. Connect to the same network as the Pi
2. Open http://pi-ip:8000/ in a browser
3. Tap your name from the crew buttons, or type a name and tap Join
4. Wait on the Standby screen until the leader engages a show or starts a rehearsal
5. Use the controls bar to adjust view, font size, line spacing, two-column layout, high contrast, transpose, and auto scroll. All settings are saved per device.
6. Tap anywhere in the content area to hide the controls bar. Tap again to bring it back.
7. To use a Bluetooth pedal, tap the gear button in the header and assign keys in the Pedal Settings panel.

---

## ChordPro format

Wrap chord names in square brackets before the syllable where they are played:

```
[G]Here comes the [Em]sun, [C]doo-doo-doo-[D]doo
[G]Here comes the [Em]sun, and I [C]say it's all-[D]right
```

Chords appear on their own line above the lyric. Lyrics view strips all chord markers. Each device transposes independently.

**Section markers** use the same bracket syntax:

```
[Verse 1]
[G]Here comes the [Em]sun

[Chorus]
[C]Come [G]together [D]right now

[Verse 2]
[G]He wear no shoeshine

[Chorus]
```

The second [Chorus] with no following content is a back-reference. It renders as a dimmed repeat cue rather than duplicating the full text.

**The Convert tool** accepts chords-above-lyrics format:

```
G           Em          C      D
Here comes the sun, doo doo doo doo
```

Paste it in, click Convert to ChordPro, and chord positions are mapped to the lyric text automatically.

---

## File import

Click Import in the Songs toolbar and select a file.

| Extension | Notes |
|---|---|
| .pdf | Born-digital PDFs only. Scanned image PDFs have no extractable text. |
| .txt | Plain text. Use the Convert tool to convert to ChordPro. |
| .chopro / .cho / .crd / .chordpro / .pro | ChordPro format, imports directly. |

A preview modal lets you edit the content and choose whether to place it in the Chords or Lyrics field before creating the song. The song editor opens automatically after import.

**Pi note:** pdfplumber is installed automatically by setup.sh. On an existing Pi set up before file import was added:
```bash
source venv/bin/activate && pip install pdfplumber
```

---

## CSV import

1. Click Template in the Songs toolbar to download an example file
2. Fill in your songs and save as CSV
3. Click CSV in the toolbar and select your file
4. Map each column to the correct field
5. Review the preview and click Import

| Field | Notes |
|---|---|
| Title | Required |
| Artist | Optional |
| Key | Optional, e.g. G, Am, Bb |
| Tempo | Optional, integer BPM |
| Duration | Optional, integer seconds or MM:SS |
| Status | Optional: active, needs_work, maybe, retired |

---

## Database backup and restore

**From the browser:**
Download: click the DB button in the leader nav bar.
Restore: click the upload DB button, select a .db file, and confirm.

**On the Pi:**
```bash
# Backup
cp setlist.db setlist-$(date +%Y%m%d).db

# Restore
sudo systemctl stop setlist-cmdr
cp setlist-YYYYMMDD.db setlist.db
sudo systemctl start setlist-cmdr
```

---

## Font caching for offline use

```bash
bash setup-fonts.sh
sudo systemctl restart setlist-cmdr
```

Downloads Bebas Neue, DM Mono, and DM Sans from Google Fonts into static/fonts/. After restarting, fonts load from the Pi with no internet required.

---

## Song status values

| Status | Meaning |
|---|---|
| Active | Ready to perform |
| Needs Work | Still learning or not gig-ready |
| Maybe | Possible addition to repertoire |
| Retired | Dropped from active use |

---

## Service management (Pi)

```bash
sudo systemctl status  setlist-cmdr
sudo systemctl restart setlist-cmdr
sudo systemctl stop    setlist-cmdr
sudo journalctl -u     setlist-cmdr -f
```

---

## File structure

```
setlist-cmdr/
+-- main.py                    FastAPI server, all endpoints and WebSocket
+-- run.py                     Cross-platform launcher
+-- requirements.txt           Python dependencies
+-- setlist.db                 SQLite database, auto-created on first run
+-- setup.sh                   First-time Pi setup
+-- setup-fonts.sh             Optional font cache setup
+-- start.bat                  Windows quick-start
+-- start.sh                   Linux and macOS quick-start
+-- static/
    +-- leader.html            Band leader interface
    +-- leader.css             Leader styles
    +-- musician.html          Musician stage view
    +-- monitor.html           Confidence monitor display
    +-- monitor-setup.html     Monitor configuration page
    +-- sw.js                  PWA service worker
    +-- manifest-leader.json   PWA manifest for leader
    +-- manifest-musician.json PWA manifest for musicians
    +-- fonts/                 Locally cached fonts (after setup-fonts.sh)
    +-- img/                   Logos and icons
```

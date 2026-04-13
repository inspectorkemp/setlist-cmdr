<div align="center">
<img src="static/img/logo_large.png" alt="Setlist CMDR" width="380">
</div>

# Setlist CMDR

A band setlist and song management system that runs on your local network. No internet required at the venue. Run it on a Raspberry Pi, connect all devices to the same WiFi, and everyone opens a browser. Nothing to install on phones or tablets.

The band leader controls everything from a PIN-protected web interface. Musicians see the current song in real time on their own devices. A confidence monitor page is available for a floor wedge or large TV.

---

## Quick start

**Windows:** double-click start.bat

**macOS and Linux:**
```bash
python3 run.py
```

On first run, a virtual environment is created, dependencies are installed, and the leader view opens in your browser. The default PIN is 1234.

Musicians open http://your-ip:8000/ on any device connected to the same network.

---

## What each role sees

**Band leader** (http://your-ip:8000/leader)
Full control: song library, setlists, live navigation, rehearsal mode, signals, metronome, monitor settings. PIN protected.

**Musicians** (http://your-ip:8000/)
Stage view showing the current song. Each musician independently controls their view mode, font size, transpose, capo compensation, autoscroll, and line spacing. All preferences are saved per device.

**Confidence monitor** (http://your-ip:8000/monitor)
Full-screen display for a floor wedge or large TV. Tracks the leader scroll position and transpose in real time. Scan the QR code on the standby screen to configure it from your phone.

---

## Song library

Each song stores: title, artist, key, capo, time signature, tempo, duration, status, lyrics, chords (ChordPro), and notes.

**Status levels:** Active, Needs Work, Maybe, Retired. Search by title or artist, filter by status.

**Capo** is a first-class field. Chord displays show fingered shapes adjusted for the capo position. Each device has a CAPO toggle to turn this off for players who are not using one.

**Time signature** options are 4/4, 3/4, and 6/8. The metronome uses the correct beats per bar for each song automatically.

**ChordPro format** stores chord names inline with lyrics using square brackets. The song editor includes a fullscreen split editor with live preview and a Convert tool that accepts the chords-above-lyrics format used by Ultimate Guitar and most plain-text chord sheets.

**Section markers** use the same bracket syntax as chords. Any token that is not a chord name becomes a section header: [Verse 1], [Chorus], [Bridge], etc. A bare repeat reference like a second [Chorus] with no following content renders as a dimmed cue rather than duplicating the text.

---

## View modes

The view mode button on each device cycles through four options:

**Chords** — chord-above-lyric layout (default)
**Lyrics** — plain text, no chords
**Consol** — each unique section shown once, all repeats removed
**Melody** — chord names and section markers only, no lyric text

---

## Setlists

Create multiple setlists, add songs from the library, drag to reorder, and insert section labels between songs. Running duration updates as you build. Clone any setlist as a starting point. Active and Inactive toggle lets you hide setlists you are not currently using.

To add a song to the current setlist without leaving the Songs tab, click the + Set button on any song card.

---

## Live show workflow

1. Go to Live Control, select a setlist, click Engage
2. All musician screens update immediately
3. Navigate with Prev and Next, or click any song in the queue to jump
4. Use the signal bar (or F1-F8) to send text alerts to all musicians
5. Use TAP to set BPM by tapping in tempo, then FLASH to start the synced metronome
6. End the show with End

---

## Rehearsal mode

Click Rehearse on any song in the Songs tab to push it to all musician screens without starting a live show. Musicians see a teal Rehearsal banner. End with End Rehearsal.

---

## Metronome

The leader starts the metronome and all connected devices flash in phase. When it starts, a GET READY overlay appears while the clock sync settles. After one full bar, beat numbers (1-2-3-4) pulse on screen on every device simultaneously. Beat 1 is brighter. The perimeter ring pulses behind the numbers.

Time signature is read from the current song. 3/4 cycles 1-2-3 and 6/8 cycles 1-2-3-4-5-6.

Auto-stops after a configurable timeout of 10, 15, 20, or 30 seconds.

---

## Signal messages

Eight configurable one-tap alerts: RUSHING, DRAGGING, CHORUS, BRIDGE, KEEP GOING, WRAP IT UP, HOLD HERE, EYES ON ME. Labels are editable. A large amber banner appears on all musician screens for 3 seconds. F1-F8 hotkeys on the leader.

---

## Confidence monitor

The monitor at /monitor shows the song title, key, BPM, and time signature in large type, followed by the full content, with a Next ribbon at the bottom.

**Configuring it — three ways without touching the TV:**

1. Scan the QR code on the standby screen and adjust settings on your phone
2. Open Settings in the leader nav bar and use the Confidence Monitor section
3. Open http://your-ip:8000/monitor/setup directly

**Available settings:** view mode (Chords, Lyrics, Consol, Melody), two columns, fit mode, high contrast, capo compensation, font scale, portrait (hardware rotation), rotate 90 degrees (software rotation)

**Rotate 90 degrees** uses a CSS transform to rotate the browser content 90 degrees clockwise. Use this when the TV is physically in landscape but you want portrait content. No TV or OS settings need to change.

---

## Bluetooth page turner pedals

**Leader:** Pair via Bluetooth, assign keys in Settings. Actions: Next Song, Prev Song, Scroll Down, Scroll Up. Presets for Arrow keys, Page Up/Down, and bracket keys.

**Musicians:** Tap the gear button in the header. Actions: Scroll Down, Scroll Up, Toggle view mode, Toggle autoscroll. Presets for Arrow keys and Page Up/Down.

---

## Importing songs

**Single file:** Click Import in the Songs toolbar. Supported: .pdf (born-digital only), .txt, .chopro, .cho, .crd, .chordpro, .pro, .onsong. A review modal opens before the song is created.

**Batch import:** Click Batch and select a zip file. Every supported file in the zip imports directly with duplicate detection. A results panel shows what was imported and what was skipped.

**From OnSong:** Export your library from OnSong as ChordPro or OnSong text files (use OnSong Console for bulk export), zip them, and use Batch import. Song text, chords, title, artist, key, capo, and tempo transfer correctly. Annotations, audio, and image-based charts do not.

The OnSong Archive format (.archive or .onsongarchive) is proprietary and cannot be imported.

**CSV import:** Click Template to download an example, fill in your songs, click CSV to upload, map columns, and import. Supported fields: Title, Artist, Key, Tempo, Duration, Status.

---

## Deploying to Raspberry Pi

```bash
cd setlist-cmdr
bash setup.sh
```

This installs dependencies and registers a systemd service that starts automatically on every boot.

Find your Pi's IP address:
```bash
hostname -I
```

Open the leader at http://pi-ip:8000/leader and the musician page at http://pi-ip:8000/.

After deploying updated files, always restart the service:
```bash
sudo systemctl restart setlist-cmdr
```

For the monitor browser, clear cached images and files after a restart if changes are not appearing.

---

## Confidence monitor kiosk setup

To run the monitor on a dedicated Pi, add a file at /etc/xdg/autostart/monitor.desktop:

```
[Desktop Entry]
Type=Application
Name=Monitor
Exec=chromium-browser --kiosk --noerrdialogs --disable-infobars http://main-pi-ip:8000/monitor
```

The monitor Pi needs no server. It just opens a browser pointed at the main Pi.

---

## First login and PIN

The default leader PIN is 1234. After logging in, go to Settings and set a new PIN. Sessions last 24 hours.

---

## Band member roster

Add band member names in the Crew modal. Names appear as tap-to-join buttons on the musician name screen.

---

## Database backup and restore

From the browser: click the DB button in the leader nav bar to download, or upload a backup to restore.

From the Pi:
```bash
cp setlist.db setlist-$(date +%Y%m%d).db
```

To restore:
```bash
sudo systemctl stop setlist-cmdr
cp setlist-backup.db setlist.db
sudo systemctl start setlist-cmdr
```

---

## Font caching for offline use

```bash
bash setup-fonts.sh
sudo systemctl restart setlist-cmdr
```

Caches Bebas Neue, DM Mono, and DM Sans locally. After restarting, fonts load from the Pi with no internet required.

---

## Progressive Web App

The leader and musician pages can be installed to the home screen on iPad, iPhone, and Android. Tap the share button and choose Add to Home Screen. Launches full-screen with no browser chrome.

---

## Requirements

- Python 3.9 or newer
- Raspberry Pi 3B or newer for production (works on Windows, macOS, and Linux for development)

---

## Service management

```bash
sudo systemctl status  setlist-cmdr
sudo systemctl restart setlist-cmdr
sudo systemctl stop    setlist-cmdr
sudo journalctl -u     setlist-cmdr -f
```

---

## Song status values

| Status | Meaning |
|---|---|
| Active | Ready to perform |
| Needs Work | Still learning or not gig-ready |
| Maybe | Possible addition |
| Retired | No longer in active use |

---

## ChordPro reference

```
[G]Here comes the [Em]sun, [C]doo-doo-doo-[D]doo
[G]Here comes the [Em]sun, and I [C]say it's all-[D]right
```

Chord names in square brackets sit inline before the syllable they fall on. Chords mode renders them above the lyric line. Lyrics mode strips them entirely.

Section markers use the same brackets. Any token that is not a valid chord name becomes a section header:

```
[Verse 1]
[G]Here comes the [Em]sun

[Chorus]
[C]Come [G]together [D]right now

[Chorus]
```

The second bare [Chorus] renders as a dimmed repeat cue pointing back to the first occurrence.

The Convert tool in the fullscreen editor accepts chords-above-lyrics format and maps chord positions to lyric text automatically.

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

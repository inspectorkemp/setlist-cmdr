<div align="center">
<img src="static/img/logo_large.png" alt="Setlist CMDR" width="380">
</div>

# Setlist CMDR

A full-featured setlist and song management system that runs entirely on your local network. No internet required. Run it on your PC for testing and development, then deploy to a Raspberry Pi for gigs. Musicians connect their tablets or phones to the same WiFi network and open a browser. Nothing to install on their devices.

---

## Features

**Song library**
Full management of your entire repertoire. Each song stores title, artist, key, tempo, duration, status, lyrics, chords in ChordPro format, and notes. Search by title or artist. Filter by status. Four status levels: Active, Needs Work, Maybe, and Retired.

**CSV import**
Bulk-import songs from a spreadsheet. Click the Template button in the Songs toolbar to download a correctly formatted example file. The column mapper lets you match any header to the correct field. A row preview shows the first several records before you commit. Supported fields for import: Title, Artist, Key, Tempo, Duration, and Status. Lyrics, chords, and notes must be added manually after import.

**Setlists**
Create and manage multiple setlists. Add songs from your library, drag to reorder, add section labels between songs, and see a running total duration. Rename by clicking the title or the edit button. Clone any setlist to use as a starting point. Mark setlists as Active or Inactive. Inactive setlists are hidden from the Live Control dropdown so they cannot be accidentally engaged. The setlist list itself can be reordered by dragging.

**Live Control**
Select an active setlist and hit Engage. All connected musician screens update instantly over WebSocket. Navigate with Prev and Next, or click any song in the queue to jump directly. Each musician sees the current song title, key, tempo, and a next-song ribbon. End the show with Stand Down and all musician screens return to standby.

**Rehearsal mode**
Click the Rehearse button on any song in the Songs tab to immediately send that song to all musician screens without starting a full live show. The band leader is automatically taken to the Live Control stage view showing the full song. Musicians see a purple Rehearsal banner at the top of their screen. The leader ends rehearsal with the End Rehearsal button in the control bar.

**Synced flash metronome**
The band leader starts the metronome and all connected devices flash in phase. Each device runs an NTP-style clock calibration on connect, exchanging 10 round-trip timestamps with the server, discarding the noisiest half, and averaging the rest to compute a precise clock offset. The leader broadcasts a single start message containing the BPM and an absolute epoch timestamp. Every device computes its own beat schedule from that shared epoch so drift cannot accumulate. Expected sync accuracy on a shared local network is under 10ms. A radial amber overlay pulses at tempo with a brighter accent on beat 1. Auto-stops after a configurable timeout of 10, 15, 20, or 30 seconds.

**Signal messages**
Send instant one-tap text alerts to all musician screens during a live show or rehearsal. Eight configurable slots mapped to F1 through F8 keyboard hotkeys. Default signals: RUSHING, DRAGGING, CHORUS, BRIDGE, KEEP GOING, WRAP IT UP, HOLD HERE, EYES ON ME. Labels are fully editable and saved per device. A large amber banner slides down on every musician screen and auto-dismisses after 3 seconds.

**Per-musician controls**
Each musician independently toggles between Lyrics and Chords view with the preference saved on device. A font size slider in the bottom control bar adjusts the size of the lyrics and chords text, also saved per device. Transpose chords up or down by up to 11 semitones without affecting anyone else. Toggle autoscroll to drift through lyrics at reading pace. The band leader has the same controls in their stage view.

**ChordPro chords**
Chord annotations sit inline with lyrics using square bracket notation. Transpose is applied client-side in real time.

**Musician roster**
The leader sees a live count of connected musicians in the nav bar. Clicking the count opens a popup listing each musician by name. The roster updates in real time as people join or leave.

**Database backup and restore**
Download the live SQLite database directly from the leader browser with one click. The file is timestamped automatically. Upload a previously saved backup to restore it. The server validates the file before replacing anything and saves an automatic backup of the current database first.

**iPad and Desktop modes**
A toggle in the nav bar switches between iPad mode and Desktop mode. iPad mode uses larger tap targets, bigger fonts, and press feedback instead of hover states. Desktop mode is compact and mouse-optimized. The selected mode is saved per device and defaults to iPad.

**Progressive Web App**
Both the leader and musician pages can be installed to the home screen on iPad, iPhone, and Android. Each page has its own manifest so the installed icon opens the correct URL. Once installed the app launches full-screen with no browser chrome. The interface shell loads from the device cache instantly.

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

**Testing with multiple musicians:** open additional browser tabs at `http://localhost:8000/` and enter a different name in each. Each tab acts as an independent musician screen.

The database (`setlist.db`) is created in the project folder on first run. Everything you add during PC testing carries over when you copy the folder to the Pi.

---

## Deploying to Raspberry Pi

**Requirements:**
- Raspberry Pi 3B+ or newer recommended
- Raspberry Pi OS 64-bit (Bookworm or Trixie)
- Python 3.9 or newer
- All devices connected to the same network (wired or wireless router)

**First-time setup:**
```bash
cd setlist-cmdr
bash setup.sh
```

This creates the virtual environment, installs dependencies, and registers a systemd service so Setlist CMDR starts automatically on every boot.

**Finding the Pi IP address:**
```bash
hostname -I
```

Musicians and the band leader open a browser and navigate to that IP on port 8000. For example if the Pi's IP is `192.168.1.100`:
- Leader: `http://192.168.1.100:8000/leader`
- Musicians: `http://192.168.1.100:8000/`

---

## Installing as a PWA (home screen app)

The leader and musician pages each have their own home screen icon that opens the correct page. Install them separately.

**iPad or iPhone (Safari only):**
1. Open the correct URL in Safari
2. Tap the Share button (box with arrow pointing up)
3. Tap "Add to Home Screen"
4. Tap Add

**Android (Chrome):**
1. Open the URL in Chrome
2. Tap the three-dot menu
3. Tap "Add to Home Screen" or "Install app"

---

## Band leader workflow

1. Open `http://<pi-ip>:8000/leader` in your browser or installed PWA
2. Go to the **Songs** tab and add your entire repertoire. Set tempo and key on each song so the metronome and transpose features work correctly.
3. Go to the **Setlists** tab and create a setlist for each show. Add songs, drag to reorder, and add section labels to divide the list.
4. Mark setlists you are not currently using as Inactive so they do not appear in the Live Control picker.
5. Go to the **Live Control** tab, select your setlist, and hit **Engage** when you are ready to go live.
6. During the show, use Prev and Next to navigate songs or click any song in the queue to jump directly. Use the signal bar buttons or F1 through F8 on a keyboard to send messages to musicians. Hit the Flash button to start the synced metronome on all devices.

---

## Rehearsal workflow

1. Go to the **Songs** tab
2. Find any song and click the **Rehearse** button on the right side of the song row
3. The leader view switches immediately to the Live Control stage showing the full song with lyrics, chords, and all controls active
4. All connected musician screens show the song with a purple Rehearsal banner at the top
5. When done, click **End Rehearsal** in the control bar

---

## Musician workflow

1. Connect your device to the same network as the Pi
2. Open Safari or Chrome and go to `http://<pi-ip>:8000/`
3. Enter your name and tap **JOIN**
4. The screen shows **STANDBY** until the leader engages a show or starts a rehearsal
5. Once live, your screen updates automatically every time the leader moves to a new song
6. Tap **LYRICS** or **CHORDS** to switch views (saved on your device)
7. Use the font size slider to adjust the size of the lyrics and chords text (saved on your device)
8. Tap the flat or sharp buttons to transpose independently of other musicians
9. Tap **AUTO** to start autoscrolling through lyrics

---

## ChordPro format

Wrap chord names in square brackets immediately before the syllable where they are played:

```
[G]Here comes the [Em]sun, [C]doo-doo-doo-[D]doo
[G]Here comes the [Em]sun, and I [C]say it's all-[D]right
```

In Chords view, chords are highlighted inline with the lyrics. In Lyrics view, all chord markers are stripped and only the text is shown. Transpose shifts all chords up or down on that device without affecting anyone else.

---

## Importing songs via CSV

1. Go to the **Songs** tab
2. Click the **Template** button in the toolbar to download a correctly formatted example file
3. Fill in your songs and save the file as CSV
4. Click the **CSV** button in the toolbar and select your file
5. Use the column mapper to match each column to the correct song field
6. Review the preview table showing the first several rows
7. Click **Import** to add the songs to your library

Note that the CSV importer supports Title, Artist, Key, Tempo, Duration, and Status only. Lyrics, chords, and notes must be added to each song manually after import.

**Supported import fields:**

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

**Download from the browser:**
1. Open the leader page
2. Click the **DB** download button in the top-right nav bar
3. The file downloads as `setlist-backup-YYYYMMDD-HHMMSS.db`

**Restore from the browser:**
1. Click the **DB** upload button in the top-right nav bar
2. Select a previously downloaded `.db` file
3. Confirm the prompt
4. The server validates the file, backs up the current database automatically, replaces it, and reloads the page

**Manual backup on the Pi:**
```bash
cp setlist.db setlist-$(date +%Y%m%d).db
```

**Manual restore on the Pi:**
```bash
sudo systemctl stop setlist-cmdr
cp setlist-YYYYMMDD.db setlist.db
sudo systemctl start setlist-cmdr
```

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
├── start.bat                Windows quick-start
├── start.sh                 Linux and macOS quick-start
└── static/
    ├── leader.html          Band leader interface
    ├── leader.css           All leader styles, external file
    ├── musician.html        Musician stage view
    ├── sw.js                PWA service worker
    ├── manifest-leader.json   PWA manifest for leader (start_url: /leader)
    ├── manifest-musician.json PWA manifest for musicians (start_url: /)
    └── img/
        ├── logo_large.png
        ├── logo_bottom_right_wide.png
        ├── logo_top_right.png
        ├── logo_bottom_left.png
        ├── icon-192.png
        ├── icon-512.png
        └── apple-touch-icon.png
```

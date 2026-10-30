"""
Druckregal – deine 3D-Druck-Bibliothek
Start:  python druckregal.py      (oder start.bat doppelklicken)
"""
import hashlib
import json
import zipfile
import re
import multiprocessing
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from concurrent.futures import ProcessPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote


def _ensure_deps():
    """Fehlende Bibliotheken (numpy, Pillow) beim ersten Start nachinstallieren."""
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        return
    except ImportError:
        if os.name != "nt" or __name__ != "__main__":
            raise
    import ctypes
    r = ctypes.windll.user32.MessageBoxW(
        0, "Druckregal braucht noch die Bibliotheken numpy und Pillow.\n\n"
           "Jetzt automatisch aus dem Internet installieren? (ca. 1 Minute)",
        "Druckregal", 0x04 | 0x40)
    if r != 6:
        sys.exit(1)
    py = os.path.join(os.path.dirname(sys.executable), "python.exe")
    subprocess.call([py, "-m", "pip", "install", "--no-warn-script-location", "numpy", "pillow"])
    subprocess.call([py, "-m", "pip", "install", "--no-warn-script-location", "pywebview"])
    subprocess.Popen([sys.executable] + sys.argv)
    sys.exit(0)


_ensure_deps()
import analyzer  # noqa: E402

APP = "Druckregal"
VERSION = "2.8.4"

# Änderungen je Version (neueste zuerst) – wird im Programm unter „Was ist neu?“ angezeigt
CHANGELOG = [
    {"version": "2.8.4", "date": "30.10.2026", "changes": [
        "Neu: „Mit Einstellungen öffnen …“ bei 3MF-Projekten – Schichthöhe, Füllung, Wände, Stützen, Brim, Druckplatte, Prime-Tower und Filamentfarben festlegen, bevor Bambu Studio öffnet",
        "Druckregal öffnet dafür eine Kopie mit deinen Werten – die Originaldatei bleibt unverändert",
    ]},
    {"version": "2.8.3", "date": "30.10.2026", "changes": [
        "Geändert: Ein Klick auf einen Ordner links zeigt nur die Dateien, die direkt in diesem Ordner liegen – ohne die Unterordner",
        "Neu: Beim Auswählen eines Ordners klappen links seine Unterordner auf"]},
    {"version": "2.8.2", "date": "24.10.2026", "changes": [
        "Neu: Entf-Taste löscht das ausgewählte Modell (mit Rückfrage, landet im Papierkorb)",
        "Neu: Löschen-Rückfrage lässt sich mit Enter bestätigen und mit Esc abbrechen",
        "Neu: Modelle per Gedrückthalten und Ziehen frei anordnen – die eigene Reihenfolge wird gespeichert",
        "Neu: In der Druckliste ändert Ziehen die Reihenfolge der Druckliste",
        "Geändert: Ordner (Projekte) stehen immer an erster Stelle – bei jeder Sortierung"]},
    {"version": "2.8.1", "date": "19.10.2026", "changes": [
        "Neu: Rechtsklick auf ein Modell öffnet ein Menü – z. B. zum Verschieben in einen anderen Ordner",
        "Neu: In Ordner verschieben: Ordner auswählen oder direkt einen neuen anlegen",
        "Neu: Nach einem Update startet Druckregal automatisch wieder",
        "Behoben: Der Neustart nach dem Update blieb manchmal aus, wenn das alte Fenster noch nicht ganz geschlossen war"]},
    {"version": "2.8", "date": "19.10.2026", "changes": [
        "Neu: Neu hinzugefügte Dateien stehen ganz oben und tragen ein „Neu“-Schild",
        "Neu: Das Schild verschwindet, sobald du das Modell angesehen hast (spätestens nach 14 Tagen)",
        "Neu: Hinweis „X neue Modelle seit dem letzten Mal“ mit „Alle als gesehen markieren“"]},
    {"version": "2.7.1", "date": "17.10.2026", "changes": [
        "Geändert: Test-Update – prüft, ob die automatische Update-Funktion über GitHub funktioniert",
    ]},
    {"version": "2.7", "date": "17.10.2026", "changes": [
        "Neu: Archiv – länger nicht benutzte Modelle werden aus der Liste ausgeblendet, die Dateien bleiben an ihrem Platz",
        "Neu: Zeitraum fürs Archiv einstellbar: nie, 7, 15 oder 30 Tage, 3, 6 oder 12 Monate",
        "Neu: Modelle von Hand archivieren und zurückholen, Sortierung „Zuletzt benutzt“",
    ]},
    {"version": "2.6", "date": "17.10.2026", "changes": [
        "Neu: Schalter „Ersteller-Fotos“ oben – aus: Slicer-Bilder der Dateien, an: Fotos der Ersteller (MakerWorld)",
    ]},
    {"version": "2.5", "date": "17.10.2026", "changes": [
        "Neu: Neue Designs: Klar, Weich und Galerie – mit Vorschaubildern in den Einstellungen",
        "Neu: Englische Sprache – umschaltbar unter Einstellungen → Allgemein",
        "Behoben: Projekt-Kennzeichnung behält ihre Farbe in allen Stilen",
    ]},
    {"version": "2.4.1", "date": "17.10.2026", "changes": [
        "Neu: Discord-Kontakt im Info-Reiter – Benutzername kopieren oder Discord öffnen",
    ]},
    {"version": "2.4", "date": "17.10.2026", "changes": [
        "Neu: Einstellungen in Reiter aufgeteilt – Allgemein, Design, Updates und Info",
        "Neu: Info-Reiter mit Version, Patchlog, Projektseite und Datenordner",
        "Behoben: Beim Wechsel des Farbdesigns sprang die Ansicht in die Einstellungen",
    ]},
    {"version": "2.3", "date": "17.10.2026", "changes": [
        "Neu: Portable Version als einzelne Druckregal_Portable.exe – herunterladen, doppelklicken, fertig",
        "Geändert: Die portable Version speichert ihre Daten im Ordner „Druckregal-Daten“ neben der .exe",
    ]},
    {"version": "2.2", "date": "17.10.2026", "changes": [
        "Neu: „Was ist neu?“-Button beim Update-Hinweis zeigt alle Änderungen",
        "Neu: Nach einem Update erscheint einmal eine Übersicht der Neuerungen",
        "Neu: Komplette Versionshistorie unter Einstellungen → Updates",
    ]},
    {"version": "2.1", "date": "17.10.2026", "changes": [
        "Neu: Automatische Updates über GitHub – Druckregal sucht selbst nach neuen Versionen",
        "Neu: Link zur Projektseite in den Einstellungen",
    ]},
    {"version": "2.0", "date": "16.10.2026", "changes": [
        "Geändert: Duplikate sind jetzt unter Einstellungen → Aufräumen",
    ]},
    {"version": "1.9", "date": "16.10.2026", "changes": [
        "Neu: Update-Funktion – neue Versionen werden erkannt und mit einem Klick installiert",
    ]},
    {"version": "1.8", "date": "16.10.2026", "changes": [
        "Neu: 8 Farbdesigns sowie Hell-, Dunkel- und System-Modus",
    ]},
    {"version": "1.7", "date": "16.10.2026", "changes": [
        "Neu: Duplikate finden (identisch und ähnliche Namen) und in den Papierkorb verschieben",
        "Neu: Löschen-Button in der Detailansicht",
    ]},
    {"version": "1.6", "date": "16.10.2026", "changes": [
        "Neu: Designer-Fotos aus MakerWorld-3MF als Vorschaubild, Bildergalerie, Vorschaubild wählbar",
        "Neu: Ordner mit mehreren STL-Dateien als Projekt zusammenfassen",
    ]},
    {"version": "1.5", "date": "16.10.2026", "changes": [
        "Behoben: Python-Prozesse blieben nach dem Schließen im Hintergrund",
        "Geändert: Nur noch eine Druckregal-Instanz gleichzeitig",
        "Geändert: Installer beendet ein laufendes Druckregal selbst",
    ]},
    {"version": "1.4", "date": "16.10.2026", "changes": [
        "Behoben: „Im Ordner zeigen“ öffnete bei Kommas oder Leerzeichen im Namen den falschen Ordner",
    ]},
    {"version": "1.3", "date": "16.10.2026", "changes": [
        "Neu: Dateien umbenennen (Stift-Symbol, Doppelklick oder F2)",
        "Neu: Portable Version ohne Installation",
    ]},
    {"version": "1.2", "date": "16.10.2026", "changes": [
        "Neu: Drehbare 3D-Ansicht mit Vollbild",
    ]},
    {"version": "1.1", "date": "16.10.2026", "changes": [
        "Neu: Windows-Installer und eigenes Programmsymbol",
        "Neu: „Aktualisieren“-Button (F5) und automatisches Erkennen neuer Dateien",
    ]},
    {"version": "1.0", "date": "16.10.2026", "changes": [
        "Erste Version: Bibliothek für STL, OBJ, 3MF und G-Code mit Vorschau, Druckzeit, Material und Kosten",
    ]},
]
HERE = os.path.dirname(os.path.abspath(__file__))
ICON = next((c for c in (os.path.join(HERE, "druckregal.ico"), os.path.join(HERE, "..", "druckregal.ico"))
             if os.path.exists(c)), None)
_ARG_DATA = next((sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--data"), None) \
    or os.environ.get("DRUCKREGAL_DATA")
PORTABLE = bool(_ARG_DATA) or os.path.exists(os.path.join(HERE, "..", "portable.ini"))
if _ARG_DATA:  # portable Einzel-.exe: Daten im Ordner neben der .exe
    DATA = os.path.abspath(_ARG_DATA)
    os.environ["DRUCKREGAL_DATA"] = DATA
elif PORTABLE:  # portable Version: alle Daten neben der Druckregal.exe
    DATA = os.path.abspath(os.path.join(HERE, "..", "Daten"))
elif os.name == "nt":
    DATA = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP)
else:
    DATA = os.path.join(os.path.expanduser("~"), ".druckregal")
THUMBS = os.path.join(DATA, "thumbs")
MESHES = os.path.join(DATA, "meshes")
CONFIG_FILE = os.path.join(DATA, "config.json")
CACHE_FILE = os.path.join(DATA, "cache.json")
CACHE_VERSION = 3

DEFAULT_SETTINGS = {
    "density": 1.24,        # g/cm³ (PLA)
    "infill": 15,           # % Füllung für Schätzungen
    "shell": 0.9,           # mm Wand/Deckschicht-Dicke für Schätzungen
    "rate": 22,             # g pro Stunde (Bambu Standard-Profil, grob)
    "overhead": 6,          # min Aufheizen/Kalibrieren
    "price": 20,            # € pro kg
    "color": "#E9A23B",     # Vorschaufarbe für STL/OBJ
    "slicer": "",           # Pfad zu Bambu Studio / OrcaSlicer (leer = automatisch)
    "prefer_photo": True,   # Designer-Foto (MakerWorld) als Vorschaubild bevorzugen
    "show_photos": False,   # Schalter: Ersteller-Fotos statt Slicer-Bilder auf den Kacheln
    "archive_after": 30,    # Tage ohne Nutzung bis ins Archiv (0 = nie)
    "mode": "dark",         # dark | light | auto
    "update_dir": "",       # zusätzlicher Ordner für Update-Pakete (leer = Downloads)
    "update_repo": "",      # GitHub-Projekt für Online-Updates (leer = eingebautes Projekt)
    "auto_online": True,    # automatisch online nach Updates suchen
    "seen_version": "",     # zuletzt gesehene Version (für „Neu in dieser Version“)
    "accent": "kupfer",     # Farbschema
    "style": "clean",       # Stil: clean | soft | gallery | studio
    "lang": "de",           # Sprache: de | en
}

SLICER_GUESSES = [
    r"C:\Program Files\Bambu Studio\bambu-studio.exe",
    r"C:\Program Files\OrcaSlicer\orca-slicer.exe",
    r"C:\Program Files\OrcaSlicer\OrcaSlicer.exe",
]

WINDOW = None


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def file_id(path):
    return hashlib.sha1(os.path.normcase(os.path.abspath(path)).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
#  Bibliothek
# --------------------------------------------------------------------------
class Library:
    def __init__(self):
        os.makedirs(THUMBS, exist_ok=True)
        self.lock = threading.RLock()
        cfg = _load_json(CONFIG_FILE, {})
        self.sources = cfg.get("sources", [])
        self.favorites = set(cfg.get("favorites", []))
        self.queue = cfg.get("queue", [])
        self.order = cfg.get("order", [])     # eigene Reihenfolge (per Ziehen)
        self.settings = dict(DEFAULT_SETTINGS, **cfg.get("settings", {}))
        self.covers = cfg.get("covers", {})   # gewähltes Vorschaubild je Modell
        self.usage = cfg.get("usage", {})     # zuletzt benutzt (Zeitstempel) je Modell
        self.archived = cfg.get("archived", {})  # von Hand archivierte Modelle
        self.added = cfg.get("added", {})        # neu hinzugekommene Dateien (Zeitstempel), bis angesehen
        cache = _load_json(CACHE_FILE, {})
        self.cache = cache.get("files", {}) if cache.get("v") == CACHE_VERSION else {}
        self.models = {}
        self.version = 0
        self.progress = {"scanning": False, "done": 0, "total": 0, "current": "", "last": None}
        self.scan_count = 0
        self._quiet = False
        self._rescan = threading.Event()
        self._stop = False
        now = time.time()
        for path, rec in self.cache.items():
            self.models[rec["id"]] = rec
            self.usage.setdefault(rec["id"], now)   # Schonfrist für schon bekannte Dateien
        threading.Thread(target=self._scan_loop, daemon=True).start()
        self._rescan.set()

    # ---- Persistenz
    def save_config(self):
        with self.lock:
            _save_json(CONFIG_FILE, {"sources": self.sources, "favorites": sorted(self.favorites),
                                     "queue": self.queue, "order": self.order, "settings": self.settings, "covers": self.covers,
                                     "usage": self.usage, "archived": self.archived,
                                     "added": {k: v for k, v in self.added.items()
                                               if time.time() - float(v) < NEW_DAYS * 86400}})

    def save_cache(self):
        with self.lock:
            _save_json(CACHE_FILE, {"v": CACHE_VERSION, "files": self.cache})

    # ---- Scannen
    def request_scan(self):
        self._rescan.set()

    def _scan_loop(self):
        while not self._stop:
            # alle 10 Minuten automatisch nach neuen Dateien schauen
            self._rescan.wait(timeout=600)
            self._rescan.clear()
            try:
                self._scan()
            except Exception as ex:
                print("Scan-Fehler:", ex)
            self.progress["scanning"] = False
            self.progress["current"] = ""

    def _scan(self):
        self.progress.update(scanning=True, done=0, total=0, current="Suche Dateien …")
        found = {}
        for src in list(self.sources):
            for root, dirs, files in os.walk(src):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fn in files:
                    if fn.lower().endswith(analyzer.SUPPORTED) and not fn.startswith("~"):
                        p = os.path.join(root, fn)
                        try:
                            st = os.stat(p)
                        except OSError:
                            continue
                        found[p] = (st.st_mtime, st.st_size, src)
        with self.lock:
            removed = 0
            for p in list(self.cache):
                if p not in found:
                    rec = self.cache.pop(p)
                    self.models.pop(rec["id"], None)
                    removed += 1
            todo = [p for p, (mt, sz, _) in found.items()
                    if p not in self.cache or self.cache[p]["mtime"] != mt or self.cache[p]["size"] != sz
                    or (self.cache[p]["ext"] == "3mf"
                        and (self.cache[p].get("info") or {}).get("v", 1) < analyzer.INFO_VERSION)]
            upgraded = sum(1 for p in todo if p in self.cache and self.cache[p]["mtime"] == found[p][0])
            added = sum(1 for p in todo if p not in self.cache)
            # „Neu“ nur für Dateien, die in einem schon bekannten Ordner dazukommen –
            # nicht beim ersten Einlesen eines Ordners oder beim Neu-Rendern.
            known = {r["source"] for r in self.cache.values()}
            fresh = set() if self._quiet else {p for p in todo if p not in self.cache and found[p][2] in known}
            self.version += 1
        self.scan_count += 1
        last = {"id": self.scan_count, "added": added, "changed": len(todo) - added - upgraded, "removed": removed}
        if self._quiet:
            last.update(added=0, changed=0, removed=0)
            self._quiet = False
        self.progress.update(total=len(todo), done=0)
        try:
            if todo:
                # Hilfsprozesse nur während der Analyse – danach werden sie sofort beendet,
                # damit kein Speicher belegt bleibt.
                workers = max(1, min(3, (os.cpu_count() or 2) - 1, len(todo)))
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    self._analyze(pool, todo, found, fresh)
        finally:
            self.progress["last"] = last

    def _analyze(self, pool, todo, found, fresh=()):
        color = self.settings.get("color")
        futs = {}
        for p in todo:
            fid = file_id(p)
            futs[pool.submit(analyzer.analyze, p, os.path.join(THUMBS, fid), color)] = p
        last_save = time.time()
        for fut in as_completed(futs):
            p = futs[fut]
            mt, sz, src = found[p]
            try:
                info = fut.result()
            except Exception as ex:
                info = {"kind": os.path.splitext(p)[1][1:].lower(), "error": str(ex), "plates": [],
                        "filaments": [], "thumb": False}
            rec = {"id": file_id(p), "path": p, "name": os.path.splitext(os.path.basename(p))[0],
                   "ext": os.path.splitext(p)[1][1:].lower(), "mtime": mt, "size": sz, "source": src,
                   "rel": os.path.relpath(os.path.dirname(p), src).replace("\\", "/"), "info": info}
            if rec["rel"] == ".":
                rec["rel"] = ""
            with self.lock:
                self.cache[p] = rec
                self.models[rec["id"]] = rec
                self.usage.setdefault(rec["id"], time.time())
                if p in fresh:
                    self.added.setdefault(rec["id"], time.time())
                self.version += 1
            self.progress["done"] += 1
            self.progress["current"] = os.path.basename(p)
            if time.time() - last_save > 10:
                self.save_cache()
                last_save = time.time()
        self.save_cache()
        if fresh:
            self.save_config()

    def rename(self, mid, new_name):
        """Datei umbenennen (Endung bleibt). Gibt die neue ID zurück."""
        new_name = (new_name or "").strip().rstrip(". ")
        bad = set('<>:"/\\|?*') | {chr(i) for i in range(32)}
        if not new_name:
            raise ValueError("Der Name darf nicht leer sein.")
        if any(ch in bad for ch in new_name):
            raise ValueError('Diese Zeichen sind nicht erlaubt: < > : " / \\ | ? *')
        if new_name.upper() in {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}:
            raise ValueError("Dieser Name ist unter Windows reserviert.")
        with self.lock:
            rec = self.models.get(mid)
            if not rec:
                raise ValueError("Modell nicht gefunden.")
            old_path = rec["path"]
            ext = os.path.splitext(old_path)[1]
            if new_name.lower().endswith(ext.lower()):
                new_name = new_name[: -len(ext)]
            new_path = os.path.join(os.path.dirname(old_path), new_name + ext)
            if new_path == old_path:
                return mid
            if os.path.exists(new_path) and os.path.normcase(new_path) != os.path.normcase(old_path):
                raise ValueError("Es gibt in diesem Ordner schon eine Datei mit diesem Namen.")
            return self._relocate(rec, new_path)

    def _relocate(self, rec, new_path):
        """Datei verschieben/umbenennen und alle Verweise (Favorit, Liste, Bilder …) mitnehmen."""
        with self.lock:
            mid, old_path = rec["id"], rec["path"]
            shutil.move(old_path, new_path)
            nid = file_id(new_path)
            for fn in os.listdir(THUMBS):
                if fn == mid + ".png" or fn.startswith(mid + "_"):
                    try:
                        os.replace(os.path.join(THUMBS, fn), os.path.join(THUMBS, nid + fn[len(mid):]))
                    except OSError:
                        pass
            if os.path.isdir(MESHES):
                for fn in os.listdir(MESHES):
                    if fn.startswith(mid + "_"):
                        try:
                            os.remove(os.path.join(MESHES, fn))
                        except OSError:
                            pass
            st = os.stat(new_path)
            self.cache.pop(old_path, None)
            self.models.pop(mid, None)
            src = self.source_of(new_path)
            moves = {"favorites": mid in self.favorites, "cover": self.covers.pop(mid, None),
                     "added": self.added.pop(mid, None)}
            self.favorites.discard(mid)
            self.usage.pop(mid, None)
            self.archived.pop(mid, None)
            if src is None:   # außerhalb aller Quellen → nicht mehr in der Bibliothek
                self.queue = [q for q in self.queue if q != mid]
                self.order = [q for q in self.order if q != mid]
            else:
                rel = os.path.relpath(os.path.dirname(new_path), src).replace("\\", "/")
                rec = dict(rec, id=nid, path=new_path, source=src, rel="" if rel == "." else rel,
                           name=os.path.splitext(os.path.basename(new_path))[0],
                           mtime=st.st_mtime, size=st.st_size)
                self.cache[new_path] = rec
                self.models[nid] = rec
                if moves["favorites"]:
                    self.favorites.add(nid)
                self.queue = [nid if q == mid else q for q in self.queue]
                self.order = [nid if q == mid else q for q in self.order]
                if moves["cover"] is not None:
                    self.covers[nid] = moves["cover"]
                if moves["added"] is not None:
                    self.added[nid] = moves["added"]
                self.usage[nid] = time.time()
            self.version += 1
        self.save_config()
        self.save_cache()
        return nid if src is not None else None

    def source_of(self, path):
        p = os.path.normcase(os.path.abspath(path))
        best = None
        for src in self.sources:
            sp = os.path.normcase(os.path.abspath(src))
            if p.startswith(sp.rstrip("\\/") + os.sep) and (best is None or len(src) > len(best)):
                best = src
        return best

    def move(self, ids, dest):
        """Dateien in einen anderen Ordner verschieben."""
        dest = os.path.abspath(dest or "")
        if not os.path.isdir(dest):
            raise ValueError("Zielordner nicht gefunden.")
        moved, errors = {}, []
        for mid in ids:
            rec = self.models.get(mid)
            if not rec:
                continue
            target = os.path.join(dest, os.path.basename(rec["path"]))
            if os.path.normcase(os.path.dirname(rec["path"])) == os.path.normcase(dest):
                moved[mid] = mid
                continue
            if os.path.exists(target):
                errors.append(f"{rec['name']}: Im Zielordner gibt es schon eine Datei mit diesem Namen.")
                continue
            try:
                moved[mid] = self._relocate(rec, target)
            except PermissionError:
                errors.append(f"{rec['name']}: Die Datei ist gerade geöffnet (z. B. in Bambu Studio).")
            except OSError as ex:
                errors.append(f"{rec['name']}: {ex}")
        return moved, errors

    def folders(self):
        """Alle Ordner der Quellen (für „In Ordner verschieben“)."""
        out = []
        for src in list(self.sources):
            out.append({"source": src, "rel": "", "path": src})
            for root, dirs, _ in os.walk(src):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for d in dirs:
                    p = os.path.join(root, d)
                    out.append({"source": src, "rel": os.path.relpath(p, src).replace("\\", "/"), "path": p})
                if len(out) > 3000:
                    break
        order = {src: i for i, src in enumerate(self.sources)}
        out.sort(key=lambda f: (order.get(f["source"], 0), [x.lower() for x in f["rel"].split("/")] if f["rel"] else []))
        return out

    def mkdir(self, parent, name):
        name = (name or "").strip().rstrip(". ")
        if not name or any(ch in set('<>:"/\\|?*') for ch in name):
            raise ValueError('Ungültiger Ordnername (nicht erlaubt: < > : " / \\ | ? *).')
        if self.source_of(os.path.join(parent, name)) is None:
            raise ValueError("Der Ordner muss in einer deiner Quellen liegen.")
        p = os.path.join(parent, name)
        os.makedirs(p, exist_ok=True)
        return p

    # ---- Duplikate
    def _ensure_hashes(self):
        """Inhalts-Prüfsumme nur für Dateien berechnen, deren Größe mehrfach vorkommt."""
        with self.lock:
            recs = list(self.models.values())
        by_size = {}
        for r in recs:
            by_size.setdefault(r["size"], []).append(r)
        for size, group in by_size.items():
            if len(group) < 2 or size == 0:
                continue
            for r in group:
                if r.get("hash") and r.get("hash_mtime") == r["mtime"]:
                    continue
                try:
                    h = hashlib.sha1()
                    with open(r["path"], "rb") as f:
                        for chunk in iter(lambda: f.read(1 << 20), b""):
                            h.update(chunk)
                    r["hash"], r["hash_mtime"] = h.hexdigest(), r["mtime"]
                except OSError:
                    pass

    @staticmethod
    def _base_name(name):
        n = name.lower().strip()
        for _ in range(3):
            n2 = re.sub(r"\s*[\(\[]\d{1,3}[\)\]]\s*$", "", n)          # Name(2), Name (3), Name[1]
            n2 = re.sub(r"(\s*-\s*|\s+|_)(kopie|copy)(\s*\(?\d+\)?)?$", "", n2)  # - Kopie, _copy
            n2 = re.sub(r"^(kopie von|copy of)\s+", "", n2)
            if n2 == n:
                break
            n = n2
        return re.sub(r"[\s_\-]+", " ", n).strip()

    def duplicates(self):
        self._ensure_hashes()
        with self.lock:
            recs = list(self.models.values())
        exact, seen = [], set()
        by_hash = {}
        for r in recs:
            if r.get("hash") and r.get("hash_mtime") == r["mtime"]:
                by_hash.setdefault((r["hash"], r["size"]), []).append(r)
        for g in by_hash.values():
            if len(g) > 1:
                exact.append([r["id"] for r in g])
                seen.update(r["id"] for r in g)
        by_name = {}
        for r in recs:
            by_name.setdefault((self._base_name(r["name"]), r["ext"]), []).append(r)
        similar = []
        for (base, ext), g in by_name.items():
            if len(g) < 2 or not base:
                continue
            ids = [r["id"] for r in g]
            # Gruppen, die komplett identisch sind, stehen schon bei "exakt"
            if any(set(ids) <= set(e) for e in exact):
                continue
            similar.append(ids)
        return {"exact": exact, "similar": similar}

    def delete(self, ids):
        """Dateien in den Papierkorb verschieben und aus der Bibliothek entfernen."""
        done, errors = [], []
        for mid in ids:
            rec = self.get(mid)
            if not rec:
                continue
            try:
                to_trash(rec["path"])
            except Exception as ex:
                errors.append(f"{rec['name']}: {ex}")
                continue
            done.append(mid)
            with self.lock:
                self.cache.pop(rec["path"], None)
                self.models.pop(mid, None)
                self.favorites.discard(mid)
                self.queue = [q for q in self.queue if q != mid]
                self.order = [q for q in self.order if q != mid]
                self.covers.pop(mid, None)
                self.usage.pop(mid, None)
                self.archived.pop(mid, None)
                self.added.pop(mid, None)
                self.version += 1
            for folder in (THUMBS, MESHES):
                if os.path.isdir(folder):
                    for fn in os.listdir(folder):
                        if fn.startswith(mid + ".") or fn.startswith(mid + "_"):
                            try:
                                os.remove(os.path.join(folder, fn))
                            except OSError:
                                pass
        self.save_config()
        self.save_cache()
        return done, errors

    def touch(self, mid, unarchive=True):
        """Modell als benutzt markieren (setzt die Archiv-Uhr zurück)."""
        with self.lock:
            if mid in self.models:
                self.usage[mid] = time.time()
                if unarchive:
                    self.archived.pop(mid, None)
                self.version += 1

    def rerender_meshes(self):
        """Nach Änderung der Vorschaufarbe: STL/OBJ neu rendern."""
        with self.lock:
            for p in [p for p, r in self.cache.items() if r["ext"] in ("stl", "obj")]:
                rec = self.cache.pop(p)
                self.models.pop(rec["id"], None)
            self.version += 1
            self._quiet = True
        shutil.rmtree(MESHES, ignore_errors=True)
        self.request_scan()

    # ---- Aufbereitung für die Oberfläche
    def enrich(self, rec):
        s = self.settings
        inf = rec.get("info") or {}
        out = {
            "id": rec["id"], "name": rec["name"], "ext": rec["ext"], "size": rec["size"], "mtime": rec["mtime"],
            "source": rec["source"], "rel": rec["rel"], "path": rec["path"],
            "thumb": bool(inf.get("thumb")), "sliced": bool(inf.get("sliced")),
            "dims": inf.get("dims"), "volume": inf.get("volume_mm3"), "triangles": inf.get("triangles"),
            "multicolor": bool(inf.get("multicolor")), "error": inf.get("error"),
            "printer": inf.get("printer") or "", "layer_height": inf.get("layer_height"),
            "infill": inf.get("infill"), "slicer": inf.get("slicer") or "", "title": inf.get("title") or "",
            "designer": inf.get("designer") or "", "length_m": inf.get("length_m"),
            "fav": rec["id"] in self.favorites, "queued": rec["id"] in self.queue,
            "photos": inf.get("photos") or 0,
        }
        cov = self.covers.get(rec["id"])
        if cov is None:
            cov = "m1" if out["photos"] and s.get("prefer_photo", True) else "plate"
        if cov.startswith("m") and int(cov[1:] or 0) > out["photos"]:
            cov = "plate"
        out["cover"] = cov
        out["cover_set"] = rec["id"] in self.covers
        last = max(float(self.usage.get(rec["id"], 0) or 0), float(rec.get("mtime") or 0))
        out["last_used"] = last
        days = int(s.get("archive_after") or 0)
        auto = days > 0 and time.time() - last > days * 86400 and not out["fav"] and not out["queued"]
        out["archived"] = rec["id"] in self.archived or auto
        ts = self.added.get(rec["id"])
        out["added"] = float(ts) if ts and time.time() - float(ts) < NEW_DAYS * 86400 else 0
        out["new"] = bool(out["added"])
        if out["new"]:
            out["archived"] = False
        filaments = [dict(f) for f in inf.get("filaments") or []]
        out["filaments"] = filaments
        weight, tsec, est = inf.get("weight_g"), inf.get("time_s"), False
        if not inf.get("sliced") and inf.get("volume_mm3"):
            V = inf["volume_mm3"]
            A = inf.get("area_mm2") or 0
            dens = inf.get("density") or float(s["density"])
            infill = (inf.get("infill") if inf.get("infill") is not None else float(s["infill"])) / 100.0
            shell = inf.get("shell_mm") or float(s["shell"])
            sv = min(V, A * shell)
            weight = (sv + (V - sv) * infill) * dens / 1000.0
            tsec = float(s["overhead"]) * 60 + weight / max(float(s["rate"]), 0.1) * 3600
            est = True
        out["weight"] = round(weight, 1) if weight else None
        out["time"] = round(tsec) if tsec else None
        out["estimated"] = est
        out["cost"] = round(weight / 1000 * float(s["price"]), 2) if weight else None
        out["materials"] = sorted({(f.get("type") or "").upper() for f in filaments if f.get("type")})
        plates = []
        for p in inf.get("plates") or []:
            plates.append({"index": p["index"], "time": p.get("time_s"), "weight": p.get("weight_g"),
                           "thumb": bool(p.get("thumb")), "filaments": p.get("filaments") or [],
                           "objects": p.get("objects") or [],
                           "cost": round(p["weight_g"] / 1000 * float(s["price"]), 2) if p.get("weight_g") else None})
        out["plates"] = plates
        return out

    def all_models(self):
        with self.lock:
            return [self.enrich(r) for r in self.models.values()]

    def get(self, mid):
        with self.lock:
            return self.models.get(mid)


LIB = None


# --------------------------------------------------------------------------
#  Systemaktionen
# --------------------------------------------------------------------------
def find_slicer():
    p = LIB.settings.get("slicer") or ""
    if p and os.path.exists(p):
        return p
    for g in SLICER_GUESSES:
        if os.path.exists(g):
            return g
    return ""


def to_trash(path):
    """Datei in den Windows-Papierkorb verschieben (wiederherstellbar)."""
    if not os.path.exists(path):
        raise OSError("Datei nicht gefunden")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", ctypes.c_wchar_p),
                        ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]
        buf = ctypes.create_unicode_buffer(os.path.abspath(path) + "\0")  # doppelt nullterminiert
        op = SHFILEOPSTRUCTW()
        op.wFunc = 3  # FO_DELETE
        op.pFrom = ctypes.cast(buf, ctypes.c_wchar_p)
        op.fFlags = 0x40 | 0x10 | 0x04 | 0x400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
        r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if r != 0 or op.fAnyOperationsAborted or os.path.exists(path):
            raise OSError("Konnte nicht in den Papierkorb verschoben werden (Datei geöffnet?)")
    else:
        trash = os.path.join(DATA, "Papierkorb")
        os.makedirs(trash, exist_ok=True)
        dst = os.path.join(trash, os.path.basename(path))
        i = 1
        while os.path.exists(dst):
            b, e = os.path.splitext(os.path.basename(path))
            dst = os.path.join(trash, f"{b} ({i}){e}")
            i += 1
        shutil.move(path, dst)


def _detached(args):
    """Fremdprogramm starten, das unabhängig von Druckregal weiterläuft."""
    if os.name == "nt":
        # CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW | DETACHED_PROCESS
        try:
            subprocess.Popen(args, creationflags=0x01000000 | 0x00000008, close_fds=True)
        except OSError:
            subprocess.Popen(args, creationflags=0x00000008, close_fds=True)
    else:
        subprocess.Popen(args)


def open_file(path, with_slicer=True):
    sl = find_slicer() if with_slicer else ""
    if sl:
        _detached([sl, path])
    elif os.name == "nt":
        _detached(["cmd", "/c", "start", "", path])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# --------------------------------------------------------------------------
#  Druckeinstellungen für Bambu Studio / OrcaSlicer (nur 3MF-Projekte)
# --------------------------------------------------------------------------
# Schlüssel aus Metadata/project_settings.config, die man im Fenster ändern kann.
# "process": gehört zum Prozess-Profil (wird in different_settings_to_system vermerkt)
PRINT_KEYS = {
    "layer_height":          {"kind": "float", "process": True},
    "sparse_infill_density": {"kind": "percent", "process": True},
    "sparse_infill_pattern": {"kind": "enum", "process": True},
    "wall_loops":            {"kind": "int", "process": True},
    "top_shell_layers":      {"kind": "int", "process": True},
    "bottom_shell_layers":   {"kind": "int", "process": True},
    "enable_support":        {"kind": "bool", "process": True},
    "support_type":          {"kind": "enum", "process": True},
    "brim_type":             {"kind": "enum", "process": True},
    "enable_prime_tower":    {"kind": "bool", "process": True},
    "curr_bed_type":         {"kind": "enum", "process": False},
}
PRINT_ENUMS = {
    "sparse_infill_pattern": ["grid", "gyroid", "cubic", "honeycomb", "adaptivecubic", "triangles", "tri-hexagon",
                              "crosshatch", "lightning", "zig-zag", "line", "3dhoneycomb", "concentric"],
    "support_type": ["normal(auto)", "tree(auto)", "normal(manual)", "tree(manual)"],
    "brim_type": ["auto_brim", "no_brim", "outer_only", "inner_only", "outer_and_inner", "brim_ears"],
    "curr_bed_type": ["Textured PEI Plate", "Cool Plate", "Engineering Plate", "High Temp Plate", "Supertack Plate"],
}
COPY_DIR = os.path.join(DATA, "Slicer-Kopien")


def _read_project_settings(z):
    n = next((n for n in z.namelist() if n.lower() == "metadata/project_settings.config"), None)
    if not n:
        return None, {}
    try:
        return n, json.loads(z.read(n).decode("utf-8", "replace"))
    except ValueError:
        return n, {}


def print_settings_get(path):
    """Aktuelle Druckeinstellungen einer 3MF fürs Einstellungsfenster."""
    with zipfile.ZipFile(path) as z:
        n, ps = _read_project_settings(z)
    if n is None:
        raise ValueError("Diese 3MF enthält keine Slicer-Einstellungen (nicht mit Bambu Studio / OrcaSlicer erstellt).")
    vals = {}
    for k, spec in PRINT_KEYS.items():
        v = ps.get(k)
        if isinstance(v, list):
            v = v[0] if v else None
        if v is None:
            continue
        v = str(v)
        try:
            if spec["kind"] == "float":
                vals[k] = float(v)
            elif spec["kind"] == "percent":
                vals[k] = float(v.rstrip("%"))
            elif spec["kind"] == "int":
                vals[k] = int(float(v))
            elif spec["kind"] == "bool":
                vals[k] = v.strip().lower() in ("1", "true")
            else:
                vals[k] = v
        except ValueError:
            pass
    cols = ps.get("filament_colour") or []
    types = ps.get("filament_type") or []
    fil = [{"color": c, "type": types[i] if i < len(types) else ""} for i, c in enumerate(cols)]
    return {"values": vals, "filaments": fil, "enums": PRINT_ENUMS,
            "printer": ps.get("printer_settings_id") or "", "process": ps.get("print_settings_id") or ""}


def _fmt_setting(k, v):
    kind = PRINT_KEYS[k]["kind"]
    if kind == "float":
        f = float(v)
        if not 0.04 <= f <= 1.0:
            raise ValueError("Schichthöhe muss zwischen 0,04 und 1 mm liegen")
        return ("%.3f" % f).rstrip("0").rstrip(".")
    if kind == "percent":
        f = float(v)
        if not 0 <= f <= 100:
            raise ValueError("Füllung muss zwischen 0 und 100 % liegen")
        return ("%g" % f) + "%"
    if kind == "int":
        i = int(float(v))
        if not 0 <= i <= 100:
            raise ValueError("Ungültige Anzahl")
        return str(i)
    if kind == "bool":
        return "1" if v else "0"
    v = str(v)
    if v not in PRINT_ENUMS[k]:
        raise ValueError("Ungültiger Wert für " + k)
    return v


def _drop_overrides(xml, keys):
    """Objekt-/Teil-eigene Werte für geänderte Schlüssel entfernen, damit die neuen Werte überall gelten."""
    for k in keys:
        xml = re.sub(r'[ \t]*<metadata key="%s" value="[^"]*"\s*/>\r?\n?' % re.escape(k), "", xml)
    return xml


def print_settings_apply(path, values, colors):
    """Kopie der 3MF mit geänderten Einstellungen schreiben. Das Original bleibt unverändert."""
    changes = {}
    for k, v in (values or {}).items():
        if k in PRINT_KEYS and v is not None:
            changes[k] = _fmt_setting(k, v)
    with zipfile.ZipFile(path) as z:
        n_ps, ps = _read_project_settings(z)
        if n_ps is None or not ps:
            raise ValueError("Diese 3MF enthält keine Slicer-Einstellungen.")
        changed = [k for k, v in changes.items() if str(ps.get(k)) != v]
        for k in changed:
            ps[k] = changes[k]
        if isinstance(colors, list) and isinstance(ps.get("filament_colour"), list):
            fc = ps["filament_colour"]
            for i, c in enumerate(colors[:len(fc)]):
                if isinstance(c, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", c) and c.upper() != str(fc[i]).upper():
                    fc[i] = c.upper()
        # Geänderte Prozesswerte im Profil als "abweichend" vermerken
        diff = ps.get("different_settings_to_system")
        proc = [k for k in changed if PRINT_KEYS[k]["process"]]
        if proc and isinstance(diff, list) and diff:
            have = [x for x in str(diff[0]).split(";") if x]
            diff[0] = ";".join(have + [k for k in proc if k not in have])
        base = os.path.splitext(os.path.basename(path))[0]
        os.makedirs(COPY_DIR, exist_ok=True)
        dst = os.path.join(COPY_DIR, base + ".3mf")
        i = 2
        while True:
            try:
                tmp = dst + ".tmp"
                _write_3mf_copy(z, tmp, n_ps, ps, changed)
                os.replace(tmp, dst)
                break
            except PermissionError:  # Kopie ist noch in Bambu Studio geöffnet
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                if i > 20:
                    raise
                dst = os.path.join(COPY_DIR, f"{base} ({i}).3mf")
                i += 1
    return dst


def _write_3mf_copy(z, dst, n_ps, ps, changed):
    drop_gcode = True  # alte Slice-Ergebnisse passen nicht mehr zu den neuen Einstellungen
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
        for info in z.infolist():
            n = info.filename
            low = n.lower()
            if drop_gcode and re.match(r"metadata/plate_\d+\.gcode(\.md5)?$", low):
                continue
            if n == n_ps:
                out.writestr(n, json.dumps(ps, indent=4, ensure_ascii=False))
                continue
            data = z.read(n)
            if low == "metadata/model_settings.config":
                xml = data.decode("utf-8", "replace")
                keys = list(changed)
                if "curr_bed_type" in changed:
                    keys.append("bed_type")
                xml = _drop_overrides(xml, keys)
                if drop_gcode:
                    xml = re.sub(r'(<metadata key="gcode_file" value=")[^"]*(")', r"\1\2", xml)
                data = xml.encode("utf-8")
            elif low.endswith(".rels") and drop_gcode:
                xml = data.decode("utf-8", "replace")
                xml = re.sub(r'[ \t]*<Relationship [^>]*Target="/?Metadata/plate_\d+\.gcode[^"]*"[^>]*/>\r?\n?', "", xml)
                data = xml.encode("utf-8")
            out.writestr(info, data)


def _reveal_windows(path):
    """Öffnet den Explorer im Ordner der Datei und markiert sie (Shell-API,
    funktioniert auch mit Leerzeichen, Kommas und Umlauten im Pfad)."""
    import ctypes
    from ctypes import wintypes
    path = os.path.abspath(os.path.normpath(path))
    ole32, shell32 = ctypes.windll.ole32, ctypes.windll.shell32
    ole32.CoInitialize(None)
    shell32.ILCreateFromPathW.restype = ctypes.c_void_p
    shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
    shell32.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.DWORD]
    shell32.ILFree.argtypes = [ctypes.c_void_p]
    pidl = shell32.ILCreateFromPathW(path)
    if not pidl:
        raise OSError("Pfad nicht gefunden")
    try:
        hr = shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
        if hr != 0:
            raise OSError(f"Explorer-Fehler {hr}")
    finally:
        shell32.ILFree(pidl)


def reveal_file(path):
    if os.name == "nt":
        try:
            _reveal_windows(path)
        except Exception:
            # Ersatz: ganzer Befehl als ein String, Pfad in Anführungszeichen
            _detached('explorer /select,"%s"' % os.path.normpath(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


# --------------------------------------------------------------------------
#  Updates
# --------------------------------------------------------------------------
UPDATE_FILES = {"druckregal.py", "analyzer.py", "index.html"}
# GitHub-Projekt, in dem neue Versionen veröffentlicht werden ("besitzer/projekt")
NEW_DAYS = 14   # so lange bleibt „Neu“ höchstens stehen
UPDATE_REPO = "Moerf2004/druckregal"
REMOTE_INTERVAL = 6 * 3600   # alle 6 Stunden online nachsehen
GITHUB_API = "https://api.github.com"
UPD_RX = re.compile(r"^Druckregal_Update_(\d+(?:\.\d+){1,2})\.zip$", re.I)
SETUP_RX = re.compile(r"^Druckregal_Setup_(\d+(?:\.\d+){1,2})\.exe$", re.I)


def _ver(s):
    t = tuple(int(x) for x in re.findall(r"\d+", str(s))[:3])
    return t + (0,) * (3 - len(t))


def downloads_dir():
    if os.name == "nt":
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]
            u = uuid.UUID("374DE290-123F-4565-9164-39C4925E467B")  # FOLDERID_Downloads
            g = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
            p = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0:
                path = p.value
                ctypes.windll.ole32.CoTaskMemFree(p)
                return path
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


class Updater:
    def __init__(self):
        self.available = None
        self.state = "idle"     # idle | applying | restarting | error
        self.error = ""
        self._cache = {}
        self._last_remote = 0
        self.remote_error = ""
        self.remote_checked = None
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def dirs(self):
        ds = []
        custom = (LIB.settings.get("update_dir") or "").strip()
        for d in (custom, downloads_dir(), os.path.join(HERE, "..", "Updates"), os.path.join(DATA, "updates")):
            if d and os.path.isdir(d) and os.path.abspath(d) not in ds:
                ds.append(os.path.abspath(d))
        return ds

    def _read_zip(self, path):
        st = os.stat(path)
        key = (path, st.st_mtime, st.st_size)
        if key in self._cache:
            return self._cache[key]
        info = None
        try:
            with zipfile.ZipFile(path) as z:
                man = json.loads(z.read("manifest.json").decode("utf-8"))
                files = [f for f in man.get("files", []) if f in UPDATE_FILES and f in z.namelist()]
                if files and man.get("version"):
                    clog = [c for c in man.get("changelog", []) if isinstance(c, dict)
                            and _ver(c.get("version", "0")) > _ver(VERSION)]
                    info = {"version": str(man["version"]), "notes": man.get("notes", []), "path": path,
                            "kind": "zip", "files": files, "pip": man.get("pip", []), "changelog": clog}
        except Exception:
            info = None
        self._cache[key] = info
        return info

    def check(self):
        best = None
        cur = _ver(VERSION)
        for d in self.dirs():
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for fn in names:
                p = os.path.join(d, fn)
                cand = None
                if UPD_RX.match(fn):
                    cand = self._read_zip(p)
                elif SETUP_RX.match(fn) and not PORTABLE and os.name == "nt":
                    v = SETUP_RX.match(fn).group(1)
                    cand = {"version": v, "notes": [], "path": p, "kind": "setup"}
                if cand and _ver(cand["version"]) > cur:
                    # Update-Paket bevorzugen (kleiner, ohne Installer); sonst höchste Version
                    if (best is None or _ver(cand["version"]) > _ver(best["version"])
                            or (_ver(cand["version"]) == _ver(best["version"]) and cand["kind"] == "zip")):
                        best = cand
        self.available = best
        return best

    def repo(self):
        r = (LIB.settings.get("update_repo") or UPDATE_REPO or "").strip().strip("/")
        r = re.sub(r"^https?://github\.com/", "", r)
        return r if re.fullmatch(r"[\w.-]+/[\w.-]+", r) else ""

    def check_remote(self, force=False):
        """Neueste Version aus GitHub-Releases holen und ins Update-Verzeichnis laden."""
        repo = self.repo()
        if not repo or not LIB.settings.get("auto_online", True) and not force:
            return
        if not force and time.time() - self._last_remote < REMOTE_INTERVAL:
            return
        self._last_remote = time.time()
        import urllib.request
        try:
            req = urllib.request.Request(f"{GITHUB_API}/repos/{repo}/releases/latest",
                                         headers={"Accept": "application/vnd.github+json",
                                                  "User-Agent": f"Druckregal/{VERSION}"})
            with urllib.request.urlopen(req, timeout=15) as r:
                rel = json.loads(r.read().decode("utf-8"))
            self.remote_checked = time.time()
            self.remote_error = ""
            if _ver(rel.get("tag_name", "0")) <= _ver(VERSION):
                return
            asset = next((a for a in rel.get("assets", []) if UPD_RX.match(a.get("name", ""))), None)
            if not asset:
                return
            udir = os.path.join(DATA, "updates")
            os.makedirs(udir, exist_ok=True)
            dest = os.path.join(udir, asset["name"])
            if os.path.exists(dest) and os.path.getsize(dest) == asset.get("size"):
                return
            req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": f"Druckregal/{VERSION}"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest + ".part", "wb") as f:
                shutil.copyfileobj(r, f)
            os.replace(dest + ".part", dest)
            # alte heruntergeladene Pakete aufräumen
            for fn in os.listdir(udir):
                if fn != asset["name"] and UPD_RX.match(fn):
                    try:
                        os.remove(os.path.join(udir, fn))
                    except OSError:
                        pass
        except Exception as ex:
            self.remote_error = f"Online-Prüfung nicht möglich: {ex}"

    def _loop(self):
        while True:
            try:
                if self.state == "idle":
                    self.check_remote()
                    self.check()
            except Exception as ex:
                print("Update-Prüfung:", ex)
            self._wake.wait(30)
            self._wake.clear()

    def public(self):
        a = self.available
        out = {"state": self.state, "error": self.error, "current": VERSION, "dirs": self.dirs(),
               "repo": self.repo(), "remote_error": self.remote_error, "remote_checked": self.remote_checked}
        if a:
            out["available"] = {"version": a["version"], "notes": a["notes"], "kind": a["kind"],
                                "changelog": a.get("changelog") or [],
                                "file": os.path.basename(a["path"]), "folder": os.path.dirname(a["path"])}
        return out

    def apply(self):
        a = self.check()
        if not a:
            raise ValueError("Kein Update gefunden.")
        self.state, self.error = "applying", ""
        try:
            if a["kind"] == "setup":
                _detached([a["path"]])
                self._quit_soon()
                return
            import py_compile
            import tempfile
            with zipfile.ZipFile(a["path"]) as z:
                new = {f: z.read(f) for f in a["files"]}
            # 1) neue Python-Dateien vorher prüfen
            tmpd = tempfile.mkdtemp(prefix="druckregal_upd_")
            for f, data in new.items():
                if f.endswith(".py"):
                    tp = os.path.join(tmpd, f)
                    with open(tp, "wb") as fh:
                        fh.write(data)
                    py_compile.compile(tp, doraise=True)
            # 2) benötigte Bibliotheken nachinstallieren
            if a.get("pip"):
                py = os.path.join(os.path.dirname(sys.executable), "python.exe" if os.name == "nt" else "python3")
                if not os.path.exists(py):
                    py = sys.executable
                subprocess.call([py, "-m", "pip", "install", "--disable-pip-version-check",
                                 "--no-warn-script-location"] + [str(x) for x in a["pip"]])
            # 3) Sicherung der aktuellen Version
            bdir = os.path.join(DATA, "backup", VERSION)
            os.makedirs(bdir, exist_ok=True)
            for f in UPDATE_FILES:
                src = os.path.join(HERE, f)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(bdir, f))
            # 4) Dateien ersetzen
            for f, data in new.items():
                tgt = os.path.join(HERE, f)
                with open(tgt + ".new", "wb") as fh:
                    fh.write(data)
                os.replace(tgt + ".new", tgt)
            shutil.rmtree(os.path.join(HERE, "__pycache__"), ignore_errors=True)
            shutil.rmtree(tmpd, ignore_errors=True)
            self.state = "restarting"
            self._restart()
        except Exception as ex:
            self.state, self.error = "error", f"Update fehlgeschlagen: {ex}"
            raise

    def _restart(self):
        """Nach dem Update: warten, bis dieses Fenster wirklich zu ist, dann Druckregal neu starten."""
        exe, script = sys.executable, os.path.join(HERE, "druckregal.py")
        args = [a for a in sys.argv[1:] if a != "--after-update"] + ["--after-update"]
        code = (
            "import os,sys,time,subprocess\n"
            f"pid={os.getpid()}\n"
            "if os.name=='nt':\n"
            "    import ctypes\n"
            "    k=ctypes.windll.kernel32\n"
            "    h=k.OpenProcess(0x00100000,False,pid)\n"
            "    if h:\n"
            "        k.WaitForSingleObject(h,30000); k.CloseHandle(h)\n"
            "else:\n"
            "    for _ in range(60):\n"
            "        try: os.kill(pid,0)\n"
            "        except OSError: break\n"
            "        time.sleep(0.5)\n"
            "time.sleep(0.8)\n"
            f"subprocess.Popen([{exe!r},{script!r}]+{args!r},cwd={HERE!r})\n")
        _detached([exe, "-c", code])
        self._quit_soon()

    def _quit_soon(self):
        def bye():
            time.sleep(0.8)
            try:
                LIB.save_cache()
            except Exception:
                pass
            if WINDOW is not None:
                try:
                    WINDOW.destroy()
                except Exception:
                    pass
                time.sleep(1.0)
            os._exit(0)
        threading.Thread(target=bye, daemon=True).start()


UPD = None


def pick_folder():
    if WINDOW is not None:
        import webview
        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        res = WINDOW.create_file_dialog(kind)
        if res:
            return res[0] if isinstance(res, (list, tuple)) else res
        return None
    code = ("import tkinter as t, tkinter.filedialog as f; r=t.Tk(); r.withdraw(); "
            "r.attributes('-topmost', True); print(f.askdirectory(title='Ordner mit 3D-Dateien wählen'))")
    try:
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
        return out.stdout.strip() or None
    except Exception:
        return None


# --------------------------------------------------------------------------
#  HTTP-Server
# --------------------------------------------------------------------------
LAST_PING = [time.time()]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", cache=False):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=31536000" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        LAST_PING[0] = time.time()
        if p in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                html = f.read().decode("utf-8")
            mode = re.sub(r"[^a-z]", "", str(LIB.settings.get("mode", "dark"))) or "dark"
            accent = re.sub(r"[^a-z]", "", str(LIB.settings.get("accent", "kupfer"))) or "kupfer"
            eff = "light" if mode == "light" else "dark"
            style = re.sub(r"[^a-z]", "", str(LIB.settings.get("style", "clean"))) or "clean"
            lang = "en" if LIB.settings.get("lang") == "en" else "de"
            html = html.replace('<html lang="de">',
                                f'<html lang="{lang}" data-mode="{mode}" data-accent="{accent}" data-eff="{eff}" '
                                f'data-style="{style}" data-lang="{lang}">', 1)
            return self._send(200, html, "text/html; charset=utf-8")
        if p == "/api/state":
            return self._send(200, {"version": LIB.version, "progress": LIB.progress, "sources": LIB.sources,
                                    "settings": LIB.settings, "queue": LIB.queue, "order": LIB.order, "slicer": find_slicer(),
                                    "app_version": VERSION, "portable": PORTABLE,
                                    "update": UPD.public() if UPD else None, "changelog": CHANGELOG,
                                    "data_dir": DATA})
        if p == "/api/models":
            return self._send(200, {"version": LIB.version, "models": LIB.all_models()})
        if p.startswith("/api/mesh/"):
            rec = LIB.get(p[10:])
            if not rec or rec["ext"] not in ("stl", "obj", "3mf") or not os.path.exists(rec["path"]):
                return self._send(404, {"error": "keine 3D-Daten"})
            os.makedirs(MESHES, exist_ok=True)
            fp = os.path.join(MESHES, f"{rec['id']}_{int(rec['mtime'])}.bin")
            if not os.path.exists(fp):
                for old in os.listdir(MESHES):
                    if old.startswith(rec["id"] + "_"):
                        try:
                            os.remove(os.path.join(MESHES, old))
                        except OSError:
                            pass
                data = analyzer.mesh_for_view(rec["path"], LIB.settings.get("color"))
                with open(fp + ".tmp", "wb") as f:
                    f.write(data)
                os.replace(fp + ".tmp", fp)
            with open(fp, "rb") as f:
                return self._send(200, f.read(), "application/octet-stream")
        if p.startswith("/thumb/"):
            name = os.path.basename(unquote(p[7:]))
            fp = os.path.join(THUMBS, name)
            if name.endswith((".png", ".jpg")) and os.path.exists(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "image/png" if name.endswith(".png") else "image/jpeg", cache=True)
            return self._send(404, {"error": "nicht gefunden"})
        return self._send(404, {"error": "nicht gefunden"})

    def do_POST(self):
        p = urlparse(self.path).path
        d = self._body()
        lib = LIB
        try:
            if p == "/api/pick_folder":
                return self._send(200, {"path": pick_folder()})
            if p == "/api/sources/add":
                path = os.path.abspath(d.get("path") or "")
                if not os.path.isdir(path):
                    return self._send(400, {"error": "Ordner nicht gefunden"})
                with lib.lock:
                    if path not in lib.sources:
                        lib.sources.append(path)
                lib.save_config()
                lib.request_scan()
                return self._send(200, {"ok": True})
            if p == "/api/sources/remove":
                with lib.lock:
                    if d.get("path") in lib.sources:
                        lib.sources.remove(d["path"])
                lib.save_config()
                lib.request_scan()
                return self._send(200, {"ok": True})
            if p == "/api/rescan":
                lib.request_scan()
                return self._send(200, {"ok": True})
            if p == "/api/archive":
                ids = [i for i in (d.get("ids") or []) if isinstance(i, str)]
                with lib.lock:
                    for i in ids:
                        if d.get("on"):
                            lib.archived[i] = time.time()
                        else:
                            lib.archived.pop(i, None)
                            lib.usage[i] = time.time()
                    lib.version += 1
                lib.save_config()
                return self._send(200, {"ok": True})
            if p == "/api/favorite":
                with lib.lock:
                    (lib.favorites.add if d.get("on") else lib.favorites.discard)(d.get("id"))
                    lib.version += 1
                if d.get("on"):
                    lib.touch(d.get("id"))
                lib.save_config()
                return self._send(200, {"ok": True})
            if p == "/api/seen":
                ids = d.get("ids") or ([d["id"]] if d.get("id") else [])
                with lib.lock:
                    hit = [i for i in ids if lib.added.pop(i, None) is not None]
                    if hit:
                        lib.version += 1
                if hit:
                    lib.save_config()
                return self._send(200, {"ok": True})
            if p == "/api/queue":
                with lib.lock:
                    if d.get("on") and d.get("id") not in lib.queue:
                        lib.queue.append(d.get("id"))
                    elif not d.get("on") and d.get("id") in lib.queue:
                        lib.queue.remove(d.get("id"))
                    lib.version += 1
                if d.get("on"):
                    lib.touch(d.get("id"))
                lib.save_config()
                return self._send(200, {"ok": True})
            if p == "/api/order":
                ids = [i for i in (d.get("ids") or []) if isinstance(i, str)]
                with lib.lock:
                    lib.order = list(dict.fromkeys(ids))[:100000]
                lib.save_config()
                return self._send(200, {"ok": True})
            if p == "/api/queue_order":
                ids = [i for i in (d.get("ids") or []) if isinstance(i, str)]
                with lib.lock:
                    old = set(lib.queue)
                    new = [i for i in dict.fromkeys(ids) if i in old]
                    lib.queue = new + [q for q in lib.queue if q not in set(new)]
                    lib.version += 1
                lib.save_config()
                return self._send(200, {"ok": True})
            if p == "/api/settings":
                old_color = lib.settings.get("color")
                with lib.lock:
                    for k, v in d.items():
                        if k in DEFAULT_SETTINGS:
                            lib.settings[k] = v
                    lib.version += 1
                lib.save_config()
                if lib.settings.get("color") != old_color:
                    lib.rerender_meshes()
                return self._send(200, {"ok": True})
            if p in ("/api/print_settings", "/api/open_custom"):
                rec = lib.get(d.get("id"))
                if not rec or not os.path.exists(rec["path"]):
                    return self._send(404, {"error": "Datei nicht gefunden"})
                if not rec["path"].lower().endswith(".3mf"):
                    return self._send(400, {"error": "Einstellungen gehen nur bei 3MF-Projekten"})
                try:
                    if p == "/api/print_settings":
                        return self._send(200, print_settings_get(rec["path"]))
                    dst = print_settings_apply(rec["path"], d.get("values") or {}, d.get("colors"))
                except (ValueError, OSError, zipfile.BadZipFile) as ex:
                    return self._send(400, {"error": str(ex)})
                open_file(dst)
                lib.touch(rec["id"])
                lib.save_config()
                return self._send(200, {"ok": True, "path": dst})
            if p in ("/api/open", "/api/reveal", "/api/open_default"):
                rec = lib.get(d.get("id"))
                if not rec or not os.path.exists(rec["path"]):
                    return self._send(404, {"error": "Datei nicht gefunden"})
                if p == "/api/reveal":
                    reveal_file(rec["path"])
                else:
                    open_file(rec["path"], with_slicer=(p == "/api/open"))
                lib.touch(rec["id"])
                lib.save_config()
                return self._send(200, {"ok": True})
            if p == "/api/folders":
                return self._send(200, {"folders": lib.folders()})
            if p == "/api/mkdir":
                try:
                    return self._send(200, {"path": lib.mkdir(d.get("parent") or "", d.get("name"))})
                except (ValueError, OSError) as ex:
                    return self._send(400, {"error": str(ex)})
            if p == "/api/move":
                try:
                    moved, errors = lib.move([i for i in (d.get("ids") or []) if isinstance(i, str)], d.get("dest"))
                except (ValueError, OSError) as ex:
                    return self._send(400, {"error": str(ex)})
                return self._send(200, {"moved": moved, "errors": errors})
            if p == "/api/rename":
                try:
                    nid = lib.rename(d.get("id"), d.get("name"))
                except (ValueError, OSError) as ex:
                    msg = str(ex)
                    if isinstance(ex, PermissionError):
                        msg = "Die Datei ist gerade geöffnet (z. B. in Bambu Studio) – bitte dort schließen."
                    return self._send(400, {"error": msg})
                return self._send(200, {"ok": True, "id": nid})
            if p == "/api/open_data":
                if os.name == "nt":
                    os.startfile(DATA)  # noqa
                else:
                    subprocess.Popen(["xdg-open", DATA])
                return self._send(200, {"ok": True})
            if p == "/api/open_url":
                u = str(d.get("url") or "")
                if not u.startswith(("https://github.com/", "https://discord.gg/", "https://discord.com/")):
                    return self._send(400, {"error": "Ungültige Adresse"})
                webbrowser.open(u)
                return self._send(200, {"ok": True})
            if p == "/api/update/check":
                UPD.check_remote(force=True)
                UPD.check()
                return self._send(200, UPD.public())
            if p == "/api/update/apply":
                try:
                    UPD.apply()
                except Exception as ex:
                    return self._send(400, {"error": str(ex)})
                return self._send(200, {"ok": True})
            if p == "/api/duplicates":
                return self._send(200, lib.duplicates())
            if p == "/api/delete":
                ids = [i for i in (d.get("ids") or []) if isinstance(i, str)]
                done, errors = lib.delete(ids)
                return self._send(200, {"ok": True, "deleted": done, "errors": errors})
            if p == "/api/cover":
                with lib.lock:
                    if d.get("cover"):
                        lib.covers[d.get("id")] = str(d["cover"])
                    else:
                        lib.covers.pop(d.get("id"), None)
                    lib.version += 1
                lib.save_config()
                return self._send(200, {"ok": True})
            if p == "/api/ping":
                return self._send(200, {"ok": True})
        except Exception as ex:
            return self._send(500, {"error": str(ex)})
        return self._send(404, {"error": "nicht gefunden"})


def _set_window_icon(*_):
    if os.name != "nt" or not ICON:
        return
    try:
        import ctypes
        u = ctypes.windll.user32
        u.FindWindowW.restype = ctypes.c_void_p
        u.LoadImageW.restype = ctypes.c_void_p
        u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        for _ in range(20):
            hwnd = u.FindWindowW(None, APP)
            if hwnd:
                break
            time.sleep(0.2)
        if not hwnd:
            return
        big = u.LoadImageW(None, ICON, 1, 256, 256, 0x10)
        small = u.LoadImageW(None, ICON, 1, 16, 16, 0x10)
        u.SendMessageW(hwnd, 0x80, 1, big)
        u.SendMessageW(hwnd, 0x80, 0, small)
    except Exception:
        pass


def _windows_setup():
    """Nur eine Druckregal-Instanz; Hilfsprozesse sterben immer mit dem Hauptprogramm."""
    import ctypes
    from ctypes import wintypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    # 1) Einzelinstanz: läuft Druckregal schon, dieses Fenster nach vorne holen
    k32.CreateMutexW.restype = wintypes.HANDLE
    global _MUTEX
    _MUTEX = k32.CreateMutexW(None, False, "Local\\Druckregal_Einzelinstanz")
    if k32.GetLastError() == 183 and "--after-update" in sys.argv:
        # Neustart nach einem Update: kurz warten, bis die alte Version ganz beendet ist
        for _ in range(40):
            k32.CloseHandle(wintypes.HANDLE(_MUTEX))
            time.sleep(0.5)
            _MUTEX = k32.CreateMutexW(None, False, "Local\\Druckregal_Einzelinstanz")
            if k32.GetLastError() != 183:
                break
    if k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        u32.FindWindowW.restype = wintypes.HWND
        hwnd = u32.FindWindowW(None, APP)
        if hwnd:
            u32.ShowWindow(hwnd, 9)  # SW_RESTORE
            u32.SetForegroundWindow(hwnd)
        sys.exit(0)
    # 2) Job-Objekt: beim Beenden werden alle Kindprozesse automatisch mit beendet
    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IOC(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class EXT(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IOC), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    global _JOB
    _JOB = k32.CreateJobObjectW(None, None)
    info = EXT()
    info.Basic.LimitFlags = 0x2000 | 0x800  # KILL_ON_JOB_CLOSE | BREAKAWAY_OK (für Bambu Studio)
    k32.SetInformationJobObject(wintypes.HANDLE(_JOB), 9, ctypes.byref(info), ctypes.sizeof(info))
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.AssignProcessToJobObject(wintypes.HANDLE(_JOB), k32.GetCurrentProcess())


def main():
    global LIB, WINDOW
    multiprocessing.freeze_support()
    if os.name == "nt":
        try:
            _windows_setup()
        except SystemExit:
            raise
        except Exception as ex:
            print("Windows-Setup:", ex)
    LIB = Library()
    global UPD
    UPD = Updater()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"{APP} läuft unter {url}")

    headless = "--browser" in sys.argv or "--server" in sys.argv
    try:
        if headless:
            raise ImportError
        import webview
        if os.name == "nt":
            try:  # eigenes Taskleisten-Symbol statt Python-Symbol
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Druckregal.App")
            except Exception:
                pass
        WINDOW = webview.create_window(APP, url, width=1440, height=920, min_size=(900, 600),
                                       background_color="#141416")
        WINDOW.events.shown += _set_window_icon
        webview.start()
    except ImportError:
        if "--server" not in sys.argv:
            webbrowser.open(url)
        # Beenden, wenn der Browser-Tab länger als 2 Minuten zu ist
        while "--server" in sys.argv or time.time() - LAST_PING[0] < 120:
            time.sleep(2)
    LIB._stop = True
    LIB.save_cache()
    os._exit(0)


if __name__ == "__main__":
    main()

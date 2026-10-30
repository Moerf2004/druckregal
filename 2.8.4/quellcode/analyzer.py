"""
Druckregal – Datei-Analyse
Liest STL / OBJ / 3MF (Bambu Studio / OrcaSlicer) / G-Code, extrahiert
Druckzeit, Filamentverbrauch, Maße und erzeugt Vorschaubilder.
"""
import base64
import io
import json
import math
import os
import re
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

THUMB_SIZE = 420          # Kantenlänge der gespeicherten Vorschaubilder
RENDER_SCALE = 2          # Supersampling für Kantenglättung
DEFAULT_COLOR = "#E9A23B"  # Vorschaufarbe für Modelle ohne Farbe

SUPPORTED = (".stl", ".obj", ".3mf", ".gcode")
INFO_VERSION = 2   # erhöhen, wenn neue Infos ausgelesen werden (löst Neu-Analyse aus)


# --------------------------------------------------------------------------
#  Mesh laden
# --------------------------------------------------------------------------
def load_stl(path):
    with open(path, "rb") as f:
        data = f.read()
    if len(data) >= 84:
        n = int.from_bytes(data[80:84], "little")
        if 84 + n * 50 == len(data):
            dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
            arr = np.frombuffer(data, dtype=dt, count=n, offset=84)
            return arr["v"].astype(np.float64)
    # ASCII
    nums = re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data)
    if not nums:
        return np.zeros((0, 3, 3))
    v = np.array(nums, dtype=np.float64)
    v = v[: (len(v) // 3) * 3]
    return v.reshape(-1, 3, 3)


def load_obj(path):
    verts = []
    faces = []
    with open(path, "rb") as f:
        for line in f:
            if line.startswith(b"v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith(b"f "):
                idx = []
                for tok in line.split()[1:]:
                    i = int(tok.split(b"/")[0])
                    idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    if not faces:
        return np.zeros((0, 3, 3))
    v = np.array(verts, dtype=np.float64)
    fa = np.array(faces, dtype=np.int64)
    fa = fa[(fa >= 0).all(1) & (fa < len(v)).all(1)]
    tris = v[fa]
    # OBJ ist meist Y-oben -> auf Z-oben drehen
    tris = tris[..., [0, 2, 1]] * np.array([1, -1, 1])
    return tris


_ATTR = re.compile(rb'([\w:]+)="([^"]*)"')
_UNITS = {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0,
          "inch": 25.4, "foot": 304.8, "meter": 1000.0}


def _attrs(b):
    return {k.decode(): v.decode("utf-8", "replace") for k, v in _ATTR.findall(b)}


def _parse_transform(s):
    if not s:
        return None
    try:
        m = [float(x) for x in s.split()]
        if len(m) != 12:
            return None
        return np.array(m[:9]).reshape(3, 3), np.array(m[9:])
    except ValueError:
        return None


def _apply(T, pts):
    if T is None:
        return pts
    M, t = T
    return pts @ M + t


def _combine(inner, outer):
    """erst inner, dann outer anwenden"""
    if inner is None:
        return outer
    if outer is None:
        return inner
    M1, t1 = inner
    M2, t2 = outer
    return M1 @ M2, t1 @ M2 + t2


def _floats(pairs):
    flat = b" ".join(b" ".join(p) for p in pairs)
    return np.array(flat.split(), dtype=np.float64)


class _ModelFile:
    def __init__(self, data):
        self.objects = {}
        m = re.search(rb'<model\b[^>]*\bunit="(\w+)"', data[:4000])
        self.unit = _UNITS.get(m.group(1).decode(), 1.0) if m else 1.0
        for om in re.finditer(rb"<(?:\w+:)?object\b([^>]*)>(.*?)</(?:\w+:)?object>", data, re.S):
            a = _attrs(om.group(1))
            body = om.group(2)
            oid = a.get("id")
            entry = {"mesh": None, "components": []}
            if b"<vertex" in body or b":vertex" in body:
                vs = re.findall(rb'<(?:\w+:)?vertex\s+x="([^"]+)"\s+y="([^"]+)"\s+z="([^"]+)"', body)
                if len(vs) != body.count(b"vertex "):
                    vs = []
                    for vm in re.finditer(rb"<(?:\w+:)?vertex\b([^>]*)/>", body):
                        va = _attrs(vm.group(1))
                        vs.append((va["x"].encode(), va["y"].encode(), va["z"].encode()))
                ts = re.findall(rb'<(?:\w+:)?triangle\s+v1="(\d+)"\s+v2="(\d+)"\s+v3="(\d+)"', body)
                if len(ts) != body.count(b"triangle "):
                    ts = []
                    for tm in re.finditer(rb"<(?:\w+:)?triangle\b([^>]*)/>", body):
                        ta = _attrs(tm.group(1))
                        ts.append((ta["v1"].encode(), ta["v2"].encode(), ta["v3"].encode()))
                if vs and ts:
                    v = _floats(vs).reshape(-1, 3) * self.unit
                    t = _floats(ts).astype(np.int64).reshape(-1, 3)
                    t = t[(t < len(v)).all(1)]
                    entry["mesh"] = v[t]
                entry["painted"] = b"paint_color" in body
            for cm in re.finditer(rb"<(?:\w+:)?component\b([^>]*?)/?>", body):
                ca = _attrs(cm.group(1))
                path = ca.get("p:path") or ca.get("path")
                entry["components"].append((path, ca.get("objectid"), _parse_transform(ca.get("transform"))))
            self.objects[oid] = entry
        self.items = []
        for im in re.finditer(rb"<(?:\w+:)?item\b([^>]*?)/?>", data):
            ia = _attrs(im.group(1))
            if "objectid" in ia:
                self.items.append((ia["objectid"], _parse_transform(ia.get("transform"))))
        self.meta = {}
        for mm in re.finditer(rb'<metadata\s+name="([^"]+)"\s*>([^<]*)</metadata>', data[:20000]):
            self.meta[mm.group(1).decode()] = mm.group(2).decode("utf-8", "replace").strip()


def load_3mf_mesh(z, extruder_of=None):
    """Gibt (tris, extruder_pro_dreieck, painted, metadata) zurück."""
    names = {n.lower(): n for n in z.namelist()}
    root = names.get("3d/3dmodel.model")
    if root is None:
        cands = [n for n in z.namelist() if n.lower().endswith(".model")]
        if not cands:
            return np.zeros((0, 3, 3)), np.zeros(0, int), False, {}
        root = cands[0]
    cache = {}

    def get(path):
        key = (path or root).lstrip("/")
        real = names.get(key.lower(), key)
        if real not in cache:
            try:
                cache[real] = _ModelFile(z.read(real))
            except KeyError:
                cache[real] = None
        return cache[real]

    out, ext, painted = [], [], [False]
    extruder_of = extruder_of or {}

    def walk(mf, oid, T, top_id, part_id, depth=0):
        if mf is None or depth > 8:
            return
        ob = mf.objects.get(oid)
        if ob is None:
            return
        if ob["mesh"] is not None and len(ob["mesh"]):
            pts = _apply(T, ob["mesh"].reshape(-1, 3)).reshape(-1, 3, 3)
            out.append(pts)
            e = extruder_of.get((top_id, part_id)) or extruder_of.get((top_id, None)) or 1
            ext.append(np.full(len(pts), int(e)))
            painted[0] |= ob.get("painted", False)
        for path, cid, CT in ob["components"]:
            sub = get(path) if path else mf
            walk(sub, cid, _combine(CT, T), top_id, cid if depth == 0 else part_id, depth + 1)

    rm = get(None)
    if rm is None:
        return np.zeros((0, 3, 3)), np.zeros(0, int), False, {}
    items = rm.items or [(k, None) for k in rm.objects]
    for oid, T in items:
        walk(rm, oid, T, oid, None)
    if not out:
        return np.zeros((0, 3, 3)), np.zeros(0, int), False, rm.meta
    return np.concatenate(out), np.concatenate(ext), painted[0], rm.meta


# --------------------------------------------------------------------------
#  Geometrie
# --------------------------------------------------------------------------
def mesh_stats(tris):
    if len(tris) == 0:
        return {}
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    cr = np.cross(v1 - v0, v2 - v0)
    area = 0.5 * np.linalg.norm(cr, axis=1).sum()
    vol = abs(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)
    mn = tris.reshape(-1, 3).min(0)
    mx = tris.reshape(-1, 3).max(0)
    return {"volume_mm3": float(vol), "area_mm2": float(area),
            "dims": [round(float(x), 1) for x in (mx - mn)], "triangles": int(len(tris))}


# --------------------------------------------------------------------------
#  Software-Renderer (numpy z-buffer)
# --------------------------------------------------------------------------
def _hex(c):
    c = (c or "").lstrip("#")
    if len(c) >= 6:
        try:
            return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64) / 255.0
        except ValueError:
            pass
    return _hex(DEFAULT_COLOR)


def render(tris, tri_colors=None, size=THUMB_SIZE, az=-38.0, el=26.0):
    """Rendert Dreiecke (n,3,3) zu einem transparenten PNG (PIL Image)."""
    W = H = size * RENDER_SCALE
    if len(tris) == 0:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pts = tris.reshape(-1, 3)
    mn, mx = pts.min(0), pts.max(0)
    c = (mn + mx) / 2
    a, e = math.radians(az), math.radians(el)
    Rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    p = (pts - c) @ Rz.T
    vx = p[:, 0]
    vy = p[:, 1] * math.sin(e) + p[:, 2] * math.cos(e)
    vz = -p[:, 1] * math.cos(e) + p[:, 2] * math.sin(e)   # größer = näher
    ext = max(vx.max() - vx.min(), vy.max() - vy.min(), 1e-9)
    s = (W * 0.86) / ext
    cx = W / 2 - (vx.max() + vx.min()) / 2 * s
    cy = H / 2 + (vy.max() + vy.min()) / 2 * s
    sx = (cx + vx * s).reshape(-1, 3)
    sy = (cy - vy * s).reshape(-1, 3)
    sz = vz.reshape(-1, 3)

    # Normale im View-Space
    V = np.stack([vx, vy, vz], 1).reshape(-1, 3, 3)
    n = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    ln = np.linalg.norm(n, axis=1)
    keep = ln > 1e-12
    n[keep] /= ln[keep, None]
    n[n[:, 2] < 0] *= -1  # zweiseitig beleuchten

    L1 = np.array([-0.45, 0.65, 0.62]); L1 /= np.linalg.norm(L1)
    L2 = np.array([0.7, -0.15, 0.45]); L2 /= np.linalg.norm(L2)
    Hh = L1 + np.array([0, 0, 1.0]); Hh /= np.linalg.norm(Hh)
    d1 = np.clip(n @ L1, 0, 1)
    d2 = np.clip(n @ L2, 0, 1)
    sp = np.clip(n @ Hh, 0, 1) ** 28
    if tri_colors is None:
        tri_colors = np.tile(_hex(DEFAULT_COLOR), (len(tris), 1))
    shade = 0.30 + 0.62 * d1 + 0.22 * d2
    col = np.clip(tri_colors * shade[:, None] + 0.22 * sp[:, None], 0, 1)

    # --- Rasterisierung ---
    zbuf = np.full(W * H, -np.inf)
    ibuf = np.full(W * H, -1, dtype=np.int64)
    x0, x1, x2 = sx[:, 0], sx[:, 1], sx[:, 2]
    y0, y1, y2 = sy[:, 0], sy[:, 1], sy[:, 2]
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    ix0 = np.clip(np.ceil(np.minimum(np.minimum(x0, x1), x2) - 0.5), 0, W - 1).astype(np.int64)
    ix1 = np.clip(np.floor(np.maximum(np.maximum(x0, x1), x2) - 0.5), 0, W - 1).astype(np.int64)
    iy0 = np.clip(np.ceil(np.minimum(np.minimum(y0, y1), y2) - 0.5), 0, H - 1).astype(np.int64)
    iy1 = np.clip(np.floor(np.maximum(np.maximum(y0, y1), y2) - 0.5), 0, H - 1).astype(np.int64)
    bw = ix1 - ix0 + 1
    bh = iy1 - iy0 + 1
    ok = (bw > 0) & (bh > 0) & (np.abs(den) > 1e-12)
    tri_idx_all = np.nonzero(ok)[0]
    # Gruppen nach (Breite, Höhe) in Zweierpotenzen – schmale Dreiecke bleiben billig
    gw = np.ceil(np.log2(np.maximum(bw[tri_idx_all], 1))).astype(np.int64)
    gh = np.ceil(np.log2(np.maximum(bh[tri_idx_all], 1))).astype(np.int64)
    key = gw * 64 + gh
    order_k = np.argsort(key, kind="stable")
    keys_sorted = key[order_k]
    bounds = np.flatnonzero(np.diff(keys_sorted)) + 1
    for grp in np.split(order_k, bounds):
        if not len(grp):
            continue
        k0 = key[grp[0]]
        BW, BH = 1 << int(k0 // 64), 1 << int(k0 % 64)
        sel = tri_idx_all[grp]
        oy, ox = np.mgrid[0:BH, 0:BW]
        ox = ox.ravel(); oy = oy.ravel()
        chunk = max(1, 4_000_000 // (BW * BH))
        for k in range(0, len(sel), chunk):
            t = sel[k:k + chunk]
            px = ix0[t, None] + ox[None]
            py = iy0[t, None] + oy[None]
            m = (px <= ix1[t, None]) & (py <= iy1[t, None])
            fx = px + 0.5; fy = py + 0.5
            X2 = x2[t, None]; Y2 = y2[t, None]; D = den[t, None]
            l0 = ((y1[t, None] - Y2) * (fx - X2) + (X2 - x1[t, None]) * (fy - Y2)) / D
            l1 = ((Y2 - y0[t, None]) * (fx - X2) + (x0[t, None] - X2) * (fy - Y2)) / D
            l2 = 1 - l0 - l1
            m &= (l0 >= -1e-7) & (l1 >= -1e-7) & (l2 >= -1e-7)
            if not m.any():
                continue
            zz = (l0 * sz[t, 0, None] + l1 * sz[t, 1, None] + l2 * sz[t, 2, None])[m]
            pix = (py * W + px)[m]
            tid = np.broadcast_to(t[:, None], m.shape)[m]
            order = np.lexsort((-zz, pix))
            pix, zz, tid = pix[order], zz[order], tid[order]
            first = np.ones(len(pix), bool)
            first[1:] = pix[1:] != pix[:-1]
            pix, zz, tid = pix[first], zz[first], tid[first]
            better = zz > zbuf[pix]
            zbuf[pix[better]] = zz[better]
            ibuf[pix[better]] = tid[better]

    hit = ibuf >= 0
    img = np.zeros((W * H, 4), dtype=np.float64)
    img[hit, :3] = col[ibuf[hit]]
    img[hit, 3] = 1.0
    img = img.reshape(H, W, 4)

    # Konturen an Tiefensprüngen abdunkeln
    zb = zbuf.reshape(H, W)
    zfill = np.where(np.isfinite(zb), zb, zb[np.isfinite(zb)].min() - ext if hit.any() else 0)
    gx = np.abs(np.diff(zfill, axis=1, append=zfill[:, -1:]))
    gy = np.abs(np.diff(zfill, axis=0, append=zfill[-1:, :]))
    edge = (np.maximum(gx, gy) > ext * 0.02) & hit.reshape(H, W)
    img[edge, :3] *= 0.55

    im = Image.fromarray((img * 255).astype(np.uint8), "RGBA")
    im = im.convert("RGBa").resize((size, size), Image.LANCZOS).convert("RGBA")
    return im


# --------------------------------------------------------------------------
#  Hilfen
# --------------------------------------------------------------------------
def parse_duration(s):
    """'1d 2h 3m 4s' -> Sekunden"""
    if s is None:
        return None
    s = str(s).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    tot, found = 0.0, False
    for val, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([dhms])", s):
        found = True
        tot += float(val) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    return tot if found else None


def _fnum(x):
    try:
        return float(str(x).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def save_thumb(img, path):
    img = img.copy()
    img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
    img.save(path, "PNG", optimize=True)


def _first(lst, i=0, default=None):
    if isinstance(lst, list):
        return lst[i] if i < len(lst) else (lst[0] if lst else default)
    return lst if lst is not None else default


# --------------------------------------------------------------------------
#  3MF
# --------------------------------------------------------------------------
def analyze_3mf(path, thumb_base):
    info = {"kind": "3mf", "plates": [], "filaments": [], "sliced": False}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        lower = {n.lower(): n for n in names}

        def read(name):
            n = lower.get(name.lower())
            return z.read(n) if n else None

        # Projekteinstellungen (Bambu / Orca)
        ps = {}
        raw = read("Metadata/project_settings.config")
        if raw:
            try:
                ps = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                ps = {}
        f_types = ps.get("filament_type") or []
        f_cols = ps.get("filament_colour") or []
        f_dens = ps.get("filament_density") or []
        info["printer"] = ps.get("printer_model") or ps.get("printer_settings_id") or ""
        info["layer_height"] = _fnum(ps.get("layer_height"))
        info["infill"] = _fnum(ps.get("sparse_infill_density") or ps.get("fill_density"))
        wl = _fnum(ps.get("wall_loops") or ps.get("perimeters"))
        lw = _fnum(_first(ps.get("line_width"))) or _fnum(_first(ps.get("outer_wall_line_width"))) or 0.42
        if wl:
            info["shell_mm"] = round(wl * lw + 0.1, 2)

        # Objekt/Teil -> Extruder
        extruder_of, used_ext, plate_count, obj_names = {}, set(), 0, {}
        raw = read("Metadata/model_settings.config")
        if raw:
            try:
                ms = ET.fromstring(raw)
                for ob in ms.findall("object"):
                    oid = ob.get("id")
                    for md in ob.findall("metadata"):
                        if md.get("key") == "extruder":
                            extruder_of[(oid, None)] = int(md.get("value") or 1)
                        if md.get("key") == "name":
                            obj_names[oid] = md.get("value")
                    for part in ob.findall("part"):
                        for md in part.findall("metadata"):
                            if md.get("key") == "extruder":
                                extruder_of[(oid, part.get("id"))] = int(md.get("value") or 1)
                plate_count = len(ms.findall("plate"))
            except ET.ParseError:
                pass
        used_ext = set(extruder_of.values()) or {1}

        # Slice-Info (nur wenn geslict)
        raw = read("Metadata/slice_info.config")
        if raw:
            try:
                si = ET.fromstring(raw)
                for pl in si.findall("plate"):
                    md = {m.get("key"): m.get("value") for m in pl.findall("metadata")}
                    p = {"index": int(md.get("index") or len(info["plates"]) + 1),
                         "time_s": _fnum(md.get("prediction")),
                         "weight_g": _fnum(md.get("weight")),
                         "filaments": [], "objects": []}
                    for fl in pl.findall("filament"):
                        p["filaments"].append({"id": int(fl.get("id") or 1), "type": fl.get("type") or "",
                                               "color": fl.get("color") or "", "used_g": _fnum(fl.get("used_g")),
                                               "used_m": _fnum(fl.get("used_m"))})
                    for ob in pl.findall("object"):
                        if ob.get("name"):
                            p["objects"].append(ob.get("name"))
                    if p["time_s"]:
                        info["sliced"] = True
                    info["plates"].append(p)
            except ET.ParseError:
                pass
        # Eingebetteter G-Code (falls slice_info fehlt)
        if not info["sliced"]:
            for n in names:
                if re.match(r"Metadata/plate_\d+\.gcode$", n, re.I):
                    with z.open(n) as fh:
                        head = fh.read(300_000).decode("utf-8", "replace")
                    g = _gcode_header(head)
                    if g.get("time_s"):
                        idx = int(re.findall(r"\d+", n.split("/")[-1])[0])
                        info["plates"].append({"index": idx, "time_s": g["time_s"], "weight_g": g.get("weight_g"),
                                               "filaments": [], "objects": []})
                        info["sliced"] = True
        if not info["sliced"]:
            n_pl = max(plate_count, 1)
            info["plates"] = [{"index": i + 1, "time_s": None, "weight_g": None, "filaments": [], "objects": []}
                              for i in range(n_pl)]

        # Filamentliste
        if info["sliced"]:
            agg = {}
            for p in info["plates"]:
                for f in p["filaments"]:
                    k = (f["type"], f["color"].upper())
                    a = agg.setdefault(k, {"type": f["type"], "color": f["color"], "used_g": 0.0, "used_m": 0.0})
                    a["used_g"] += f["used_g"] or 0
                    a["used_m"] += f["used_m"] or 0
            info["filaments"] = list(agg.values())
            info["time_s"] = sum(p["time_s"] or 0 for p in info["plates"])
            info["weight_g"] = sum(p["weight_g"] or 0 for p in info["plates"]) or sum(f["used_g"] for f in info["filaments"]) or None
            lm = sum(f["used_m"] for f in info["filaments"])
            info["length_m"] = round(lm, 2) if lm else None
        else:
            for e in sorted(used_ext):
                info["filaments"].append({"type": _first(f_types, e - 1, "PLA") or "",
                                          "color": _first(f_cols, e - 1, "") or "",
                                          "used_g": None, "used_m": None})
        de = _fnum(_first(f_dens, min(used_ext) - 1))
        if de:
            info["density"] = de

        # Vorschaubilder
        thumb_ok = False
        plate_imgs = {}
        for n in names:
            m = re.match(r"Metadata/plate_(\d+)\.png$", n, re.I)
            if m:
                plate_imgs[int(m.group(1))] = n
        for idx, n in sorted(plate_imgs.items()):
            try:
                im = Image.open(io.BytesIO(z.read(n))).convert("RGBA")
                save_thumb(im, f"{thumb_base}_p{idx}.png")
                for p in info["plates"]:
                    if p["index"] == idx:
                        p["thumb"] = True
                if not thumb_ok:
                    save_thumb(im, f"{thumb_base}.png")
                    thumb_ok = True
            except Exception:
                pass
        if not thumb_ok:
            for cand in ("Metadata/thumbnail.png", "Auxiliaries/.thumbnails/thumbnail_middle.png",
                         "Auxiliaries/.thumbnails/thumbnail_3mf.png", "Metadata/top_1.png"):
                d = read(cand)
                if d:
                    try:
                        save_thumb(Image.open(io.BytesIO(d)).convert("RGBA"), f"{thumb_base}.png")
                        thumb_ok = True
                        break
                    except Exception:
                        pass

        # Mesh (Maße, Volumen, ggf. Vorschau)
        need_mesh = (not thumb_ok) or (not info["sliced"]) or os.path.getsize(path) < 120_000_000
        painted = False
        if need_mesh:
            tris, ext, painted, meta = load_3mf_mesh(z, extruder_of)
            info.update(mesh_stats(tris))
            info["title"] = meta.get("Title") or ""
            info["designer"] = meta.get("Designer") or ""
            app = meta.get("Application") or ""
            info["slicer"] = app.split("-")[0] if app else ""
            if not thumb_ok and len(tris):
                cols = np.array([_hex(_first(f_cols, int(e) - 1, DEFAULT_COLOR)) for e in range(1, max(ext.max(), 1) + 1)])
                save_thumb(render(tris, cols[ext - 1]), f"{thumb_base}.png")
                thumb_ok = True
        info["thumb"] = thumb_ok

        # Fotos vom Designer (MakerWorld: Auxiliaries/Model Pictures)
        pics = sorted((n for n in names if n.lower().startswith("auxiliaries/model pictures/")
                       and n.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp", "bmp")),
                      key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)])
        n_ok = 0
        for n in pics[:12]:
            try:
                im = Image.open(io.BytesIO(z.read(n)))
                im = im.convert("RGB")
                im.thumbnail((1000, 1000), Image.LANCZOS)
                n_ok += 1
                im.save(f"{thumb_base}_m{n_ok}.jpg", "JPEG", quality=86, optimize=True)
            except Exception:
                pass
        info["photos"] = n_ok
        cols_used = {(f.get("color") or "").upper() for f in info["filaments"] if f.get("color")}
        info["multicolor"] = len(cols_used) > 1 or (painted and len(f_cols) > 1)
    return info


# --------------------------------------------------------------------------
#  G-Code
# --------------------------------------------------------------------------
def _gcode_header(text):
    g = {}
    m = re.search(r";\s*total estimated time:\s*([^;\n]+)", text) or \
        re.search(r";\s*estimated printing time \(normal mode\)\s*=\s*([^\n]+)", text) or \
        re.search(r";\s*model printing time:\s*([^;\n]+)", text)
    if m:
        g["time_s"] = parse_duration(m.group(1))
    else:
        m = re.search(r";TIME:(\d+)", text)
        if m:
            g["time_s"] = float(m.group(1))
    m = re.search(r";\s*total filament weight \[g\]\s*[:=]\s*([\d.]+)", text) or \
        re.search(r";\s*(?:total )?filament used \[g\]\s*=\s*([\d.]+)", text)
    if m:
        g["weight_g"] = float(m.group(1))
    m = re.search(r";\s*total filament length \[mm\]\s*[:=]\s*([\d.]+)", text) or \
        re.search(r";\s*(?:total )?filament used \[mm\]\s*=\s*([\d.]+)", text)
    if m:
        g["length_m"] = float(m.group(1)) / 1000
    else:
        m = re.search(r";Filament used:\s*([\d.]+)m", text)
        if m:
            g["length_m"] = float(m.group(1))
    m = re.search(r";\s*filament_type\s*=\s*([^\n]+)", text)
    if m:
        g["ftype"] = m.group(1).strip().split(";")[0]
    m = re.search(r";\s*filament_colou?r\s*=\s*([^\n]+)", text)
    if m:
        g["fcolors"] = [c for c in m.group(1).strip().split(";") if c]
    m = re.search(r";\s*layer_height\s*=\s*([\d.]+)", text)
    if m:
        g["layer_height"] = float(m.group(1))
    m = re.search(r";\s*printer_model\s*=\s*([^\n]+)", text)
    if m:
        g["printer"] = m.group(1).strip()
    return g


def analyze_gcode(path, thumb_base):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(3_000_000).decode("utf-8", "replace")
        if size > 3_000_000:
            f.seek(max(0, size - 1_500_000))
            tail = f.read().decode("utf-8", "replace")
        else:
            tail = ""
    text = head + "\n" + tail
    g = _gcode_header(text)
    info = {"kind": "gcode", "sliced": bool(g.get("time_s")), "time_s": g.get("time_s"),
            "weight_g": g.get("weight_g"), "length_m": round(g["length_m"], 2) if g.get("length_m") else None,
            "layer_height": g.get("layer_height"), "printer": g.get("printer", ""), "plates": [], "filaments": []}
    cols = g.get("fcolors") or []
    info["filaments"] = [{"type": g.get("ftype", ""), "color": cols[0] if cols else "",
                          "used_g": g.get("weight_g"), "used_m": info["length_m"]}]
    info["multicolor"] = len(set(c.upper() for c in cols)) > 1 and ("T1" in head or "M620" in head)
    # eingebettete Thumbnails
    best = None
    for m in re.finditer(r"; thumbnail(?:_PNG)? begin (\d+)x(\d+) \d+\n(.*?); thumbnail(?:_PNG)? end", head, re.S):
        w = int(m.group(1))
        if best is None or w > best[0]:
            best = (w, m.group(3))
    info["thumb"] = False
    if best:
        try:
            data = base64.b64decode("".join(l.lstrip("; ").strip() for l in best[1].splitlines()))
            save_thumb(Image.open(io.BytesIO(data)).convert("RGBA"), f"{thumb_base}.png")
            info["thumb"] = True
        except Exception:
            pass
    return info


# --------------------------------------------------------------------------
#  Einstieg
# --------------------------------------------------------------------------
def analyze(path, thumb_base, color=DEFAULT_COLOR):
    """Analysiert eine Datei. Läuft in einem Worker-Prozess."""
    global DEFAULT_COLOR
    DEFAULT_COLOR = color or DEFAULT_COLOR
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".3mf":
            info = analyze_3mf(path, thumb_base)
        elif ext == ".gcode":
            info = analyze_gcode(path, thumb_base)
        else:
            tris = load_stl(path) if ext == ".stl" else load_obj(path)
            info = {"kind": ext[1:], "sliced": False, "plates": [], "filaments": [], "multicolor": False}
            info.update(mesh_stats(tris))
            if len(tris):
                save_thumb(render(tris), f"{thumb_base}.png")
                info["thumb"] = True
            else:
                info["thumb"] = False
        info["error"] = None
        info["v"] = INFO_VERSION
    except Exception as ex:  # defekte Datei – trotzdem auflisten
        info = {"kind": ext[1:], "sliced": False, "plates": [], "filaments": [], "thumb": False,
                "multicolor": False, "error": f"{type(ex).__name__}: {ex}"}
    return info


# --------------------------------------------------------------------------
#  Mesh für die 3D-Ansicht (Binärformat für den Browser)
# --------------------------------------------------------------------------
MAX_VIEW_TRIS = 2_500_000


def mesh_for_view(path, color=DEFAULT_COLOR):
    """Liefert bytes: uint32 n | float32 n*9 Positionen | uint8 n*3 Farben."""
    ext = os.path.splitext(path)[1].lower()
    cols = None
    if ext == ".3mf":
        with zipfile.ZipFile(path) as z:
            names = {n.lower(): n for n in z.namelist()}
            f_cols, extruder_of = [], {}
            if "metadata/project_settings.config" in names:
                try:
                    ps = json.loads(z.read(names["metadata/project_settings.config"]).decode("utf-8", "replace"))
                    f_cols = ps.get("filament_colour") or []
                except ValueError:
                    pass
            if "metadata/model_settings.config" in names:
                try:
                    ms = ET.fromstring(z.read(names["metadata/model_settings.config"]))
                    for ob in ms.findall("object"):
                        oid = ob.get("id")
                        for md in ob.findall("metadata"):
                            if md.get("key") == "extruder":
                                extruder_of[(oid, None)] = int(md.get("value") or 1)
                        for part in ob.findall("part"):
                            for md in part.findall("metadata"):
                                if md.get("key") == "extruder":
                                    extruder_of[(oid, part.get("id"))] = int(md.get("value") or 1)
                except ET.ParseError:
                    pass
            tris, ext_idx, _, _ = load_3mf_mesh(z, extruder_of)
        if len(tris):
            pal = np.array([_hex(_first(f_cols, e - 1, color) or color) for e in range(1, int(ext_idx.max()) + 1)])
            cols = pal[ext_idx - 1]
    elif ext == ".stl":
        tris = load_stl(path)
    elif ext == ".obj":
        tris = load_obj(path)
    else:
        tris = np.zeros((0, 3, 3))
    if cols is None:
        cols = np.tile(_hex(color), (len(tris), 1))
    if len(tris) > MAX_VIEW_TRIS:  # sehr große Modelle ausdünnen
        sel = np.random.default_rng(0).choice(len(tris), MAX_VIEW_TRIS, replace=False)
        sel.sort()
        tris, cols = tris[sel], cols[sel]
    n = len(tris)
    return (np.uint32(n).tobytes() + tris.astype("<f4").tobytes()
            + (np.clip(cols, 0, 1) * 255).astype(np.uint8).tobytes())

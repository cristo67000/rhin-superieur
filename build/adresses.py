# -*- coding: utf-8 -*-
"""Index d'adresses hors ligne : Bas-Rhin (BAN) + pays de Bade (OpenStreetMap).

Sources :
  - France : Base Adresse Nationale, export départemental 67 (licence ouverte) ;
  - Allemagne : objets OSM porteurs de `addr:housenumber` dans les huit Kreise
    (Overpass, sortie CSV, centre des bâtiments), lieux habités `place=*`.

Produit :
  - data/adresses.bin  : paquet binaire gzippé lu par adresses.js
        en-tête JSON (communes, suffixes, rues avec bornes) + 4 tableaux
        alignés (numéro u16, suffixe u16, lon i32, lat i32 en millionièmes) ;
        découpé en morceaux de 48 Mo comme les tuiles (data/adresses/…) ;
  - data/communes.json : villes, villages et hameaux des deux pays pour la
        recherche de localités (léger, précaché).

Usage : python build/adresses.py
"""
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import struct
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(RACINE, "build", "cache")
DATA = os.path.join(RACINE, "data")
UA = "rhin-superieur-build/1.0 (carte hors ligne ; contact : cristo67000 sur GitHub)"
TAILLE_MORCEAU = 48_000_000

BAN_URL = "https://adresse.data.gouv.fr/data/ban/adresses/latest/csv/adresses-67.csv.gz"
KREISE = ["Freiburg im Breisgau", "Landkreis Breisgau-Hochschwarzwald", "Landkreis Emmendingen", "Ortenaukreis",
          "Landkreis Rastatt", "Baden-Baden", "Karlsruhe", "Landkreis Karlsruhe"]
MIROIRS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.private.coffee/api/interpreter"]


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- téléchargements
def telecharger_fichier(url, nom):
    os.makedirs(CACHE, exist_ok=True)
    chemin = os.path.join(CACHE, nom)
    if os.path.exists(chemin) and os.path.getsize(chemin) > 0:
        return chemin
    log("  téléchargement :", url)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(chemin + ".part", "wb") as f:
        while True:
            bloc = r.read(1 << 20)
            if not bloc:
                break
            f.write(bloc)
    os.replace(chemin + ".part", chemin)
    return chemin


def overpass(requete, nom):
    chemin = os.path.join(CACHE, nom)
    if os.path.exists(chemin) and os.path.getsize(chemin) > 0:
        return open(chemin, encoding="utf-8").read()
    derniere = None
    for url in MIROIRS:
        for essai in range(2):
            try:
                log(f"  Overpass {url.split('/')[2]} (essai {essai + 1}) : {nom}")
                req = urllib.request.Request(url, data=("data=" + urllib.parse.quote(requete)).encode(),
                                             headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=1200) as r:
                    texte = r.read().decode("utf-8")
                if texte.startswith("<?xml") or "runtime error" in texte[:2000]:
                    raise RuntimeError("réponse d'erreur Overpass : " + texte[:200])
                with open(chemin, "w", encoding="utf-8") as f:
                    f.write(texte)
                return texte
            except Exception as e:
                derniere = e
                log("    échec :", str(e)[:200])
                time.sleep(10)
    raise RuntimeError(f"Overpass a échoué pour {nom} : {derniere}")


def polygone_kreis(nom):
    """Polygone simplifié (chaîne 'lat lon lat lon…') depuis le cache Nominatim d'emprise.py."""
    from shapely.geometry import shape
    chemin = os.path.join(CACHE, "limite-" + nom.replace(" ", "_") + ".geojson")
    gj = json.load(open(chemin, encoding="utf-8"))
    for f in gj["features"]:
        if f["geometry"]["type"] in ("Polygon", "MultiPolygon"):
            g = shape(f["geometry"]).buffer(0.004).simplify(0.002)
            if g.geom_type == "MultiPolygon":
                g = max(g.geoms, key=lambda x: x.area)
            return " ".join(f"{y:.4f} {x:.4f}" for x, y in g.exterior.coords), g
    raise RuntimeError("polygone introuvable pour " + nom)


def morceaux_polygone(poly, pas=0.2):
    """Découpe un grand polygone en cellules de `pas` degrés : les serveurs Overpass
    publics rejettent (502/504) les requêtes d'adresses sur un Kreis entier."""
    from shapely.geometry import box
    if poly.area < 0.06:
        return [poly]
    lon0, lat0, lon1, lat1 = poly.bounds
    morceaux = []
    lat = math.floor(lat0 / pas) * pas
    while lat < lat1:
        lon = math.floor(lon0 / pas) * pas
        while lon < lon1:
            cellule = poly.intersection(box(lon, lat, lon + pas, lat + pas))
            if not cellule.is_empty:
                geoms = cellule.geoms if cellule.geom_type == "MultiPolygon" else [cellule]
                for g in geoms:
                    if g.geom_type == "Polygon" and g.area > 1e-6:
                        morceaux.append(g)
            lon += pas
        lat += pas
    return morceaux


def texte_poly(g):
    return " ".join(f"{y:.4f} {x:.4f}" for x, y in g.exterior.coords)


# ---------------------------------------------------------------- normalisation
def normaliser(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.lower().strip())


RE_NUMERO = re.compile(r"^\s*(\d{1,5})\s*(.*)$")


def decouper_numero(texte):
    """'12 bis' → (12, 'bis') ; '12a' → (12, 'a') ; '12-14' → (12, '-14') ; 'sans' → (0, texte)."""
    m = RE_NUMERO.match(texte or "")
    if not m:
        return 0, (texte or "").strip()[:12]
    return min(int(m.group(1)), 65535), m.group(2).strip().replace(" ", "")[:12]


# ---------------------------------------------------------------- collecte
class Collecte:
    def __init__(self):
        self.communes = {}      # (pays, nom) -> idx
        self.communes_liste = []  # [nom, pays, somme_lon, somme_lat, n, cp]
        self.reps = {"": 0}
        self.reps_liste = [""]
        self.rues = {}          # (commune_idx, nom_voie) -> idx
        self.rues_liste = []    # [nom, commune_idx, cp]
        self.adresses = []      # (rue_idx, numero, rep_idx, lon_e6, lat_e6)

    def commune(self, pays, nom, cp, lon, lat):
        cle = (pays, nom)
        if cle not in self.communes:
            self.communes[cle] = len(self.communes_liste)
            self.communes_liste.append([nom, pays, 0.0, 0.0, 0, cp or ""])
        i = self.communes[cle]
        c = self.communes_liste[i]
        c[2] += lon; c[3] += lat; c[4] += 1
        if not c[5] and cp:
            c[5] = cp
        return i

    def rep(self, texte):
        if texte not in self.reps:
            self.reps[texte] = len(self.reps_liste)
            self.reps_liste.append(texte)
        return self.reps[texte]

    def ajouter(self, pays, commune, cp, voie, numero_texte, lon, lat):
        if not voie or not commune or lon is None or lat is None:
            return
        ci = self.commune(pays, commune, cp, lon, lat)
        cle = (ci, voie)
        if cle not in self.rues:
            self.rues[cle] = len(self.rues_liste)
            self.rues_liste.append([voie, ci, cp or ""])
        ri = self.rues[cle]
        numero, suffixe = decouper_numero(numero_texte)
        self.adresses.append((ri, numero, self.rep(suffixe), int(round(lon * 1e6)), int(round(lat * 1e6))))


def charger_ban(col):
    chemin = telecharger_fichier(BAN_URL, "adresses-67.csv.gz")
    n = 0
    with gzip.open(chemin, "rt", encoding="utf-8", newline="") as f:
        lecteur = csv.DictReader(f, delimiter=";")
        for ligne in lecteur:
            try:
                lon = float(ligne["lon"]); lat = float(ligne["lat"])
            except (ValueError, KeyError):
                continue
            voie = (ligne.get("nom_voie") or "").strip()
            if not voie:
                voie = (ligne.get("nom_ld") or "").strip()
            numero = (ligne.get("numero") or "").strip()
            rep = (ligne.get("rep") or "").strip()
            commune = (ligne.get("nom_commune") or "").strip()
            cp = (ligne.get("code_postal") or "").strip()
            col.ajouter("FR", commune, cp, voie, (numero + " " + rep).strip(), lon, lat)
            n += 1
    log(f"  BAN 67 : {n:,} adresses")

def telecharger_adresses_kreis(nom, poly_txt, poly):
    """CSV Overpass des adresses d'un Kreis, cellule par cellule s'il est grand (cache)."""
    slug = re.sub(r"[^a-z]+", "-", normaliser(nom))
    parties = morceaux_polygone(poly)
    if len(parties) == 1:
        req = ('[out:csv(::lat,::lon,"addr:housenumber","addr:street","addr:place","addr:postcode","addr:city";false;"\t")]'
               '[timeout:600];'
               f'nwr["addr:housenumber"](poly:"{poly_txt}");out center qt;')
        return overpass(req, f"adresses-{slug}.tsv")
    log(f"  {nom} : {len(parties)} cellules")
    texte = ""
    for i, partie in enumerate(parties):
        req = ('[out:csv(::lat,::lon,"addr:housenumber","addr:street","addr:place","addr:postcode","addr:city";false;"\t")]'
               '[timeout:600];'
               f'nwr["addr:housenumber"](poly:"{texte_poly(partie)}");out center qt;')
        texte += overpass(req, f"adresses-{slug}-{i:02d}.tsv") + "\n"
    return texte


def charger_osm_bade(col):
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    lieux = []  # (nom, lon, lat, type, population)
    for nom in KREISE:
        poly_txt, poly = polygone_kreis(nom)
        slug = re.sub(r"[^a-z]+", "-", normaliser(nom))
        req_lieux = ('[out:csv(::lat,::lon,name,place,population;false;"\t")][timeout:300];'
                     f'node[place~"^(city|town|village|hamlet|suburb|quarter|neighbourhood)$"][name](poly:"{poly_txt}");out qt;')
        texte = overpass(req_lieux, f"lieux-{slug}.tsv")
        for ligne in csv.reader(io.StringIO(texte), delimiter="\t"):
            if len(ligne) < 4 or not ligne[2]:
                continue
            try:
                pop = int(re.sub(r"\D", "", ligne[4])) if len(ligne) > 4 and ligne[4] else 0
                lieux.append((ligne[2], float(ligne[1]), float(ligne[0]), ligne[3], pop))
            except ValueError:
                pass
    # dédoublonnage des lieux (un même village peut tomber dans deux polygones élargis)
    vus = {}
    for l in lieux:
        cle = (normaliser(l[0]), round(l[1], 2), round(l[2], 2))
        if cle not in vus:
            vus[cle] = l
    lieux = list(vus.values())
    log(f"  OSM Bade : {len(lieux):,} lieux habités")
    gros = [l for l in lieux if l[3] in ("city", "town", "village")]
    arbre = STRtree([Point(l[1], l[2]) for l in gros])

    def commune_proche(lon, lat):
        i = arbre.nearest(Point(lon, lat))
        return gros[i][0] if i is not None else ""

    total = 0
    vues = set()   # (ville, voie, numéro) normalisés : les marges des Kreise se chevauchent
    for nom in KREISE:
        poly_txt, poly = polygone_kreis(nom)
        slug = re.sub(r"[^a-z]+", "-", normaliser(nom))
        texte = telecharger_adresses_kreis(nom, poly_txt, poly)
        n = 0
        for ligne in csv.reader(io.StringIO(texte), delimiter="\t"):
            if len(ligne) < 7:
                continue
            try:
                lat = float(ligne[0]); lon = float(ligne[1])
            except ValueError:
                continue
            if not poly.contains(Point(lon, lat)):
                continue
            numero, voie, place, cp, ville = ligne[2].strip(), ligne[3].strip(), ligne[4].strip(), ligne[5].strip(), ligne[6].strip()
            if not voie:
                voie = place
            if not voie:
                continue
            if not ville:
                ville = commune_proche(lon, lat)
            cle = (normaliser(ville), normaliser(voie), normaliser(numero))
            if cle in vues:
                continue
            vues.add(cle)
            col.ajouter("DE", ville, cp, voie, numero, lon, lat)
            n += 1
        total += n
        log(f"  {nom} : {n:,} adresses")
    log(f"  OSM Bade : {total:,} adresses")
    return lieux


# ---------------------------------------------------------------- écriture
def ecrire_index(col, lieux_de):
    # tri par rue puis numéro, calcul des bornes de chaque rue
    col.adresses.sort(key=lambda a: (a[0], a[1], col.reps_liste[a[2]]))
    rues = []
    debut = 0
    n_total = len(col.adresses)
    k = 0
    for ri, r in enumerate(col.rues_liste):
        j = k
        lon_min = lat_min = 1 << 31; lon_max = lat_max = -(1 << 31)
        while j < n_total and col.adresses[j][0] == ri:
            a = col.adresses[j]
            lon_min = min(lon_min, a[3]); lon_max = max(lon_max, a[3])
            lat_min = min(lat_min, a[4]); lat_max = max(lat_max, a[4])
            j += 1
        rues.append([r[0], r[1], r[2], k, j - k, lon_min, lat_min, lon_max, lat_max])
        k = j
    communes = [[c[0], c[1], round(c[2] / c[4], 5), round(c[3] / c[4], 5), c[5]] for c in col.communes_liste]
    entete = {"version": 1, "n": n_total, "communes": communes, "reps": col.reps_liste, "rues": rues,
              "sources": {"FR": "Base Adresse Nationale (licence ouverte)", "DE": "OpenStreetMap (ODbL)"},
              "date": time.strftime("%Y-%m-%d")}
    entete_octets = json.dumps(entete, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    numeros = struct.pack("<%dH" % n_total, *[a[1] for a in col.adresses])
    reps = struct.pack("<%dH" % n_total, *[a[2] for a in col.adresses])
    lons = struct.pack("<%di" % n_total, *[a[3] for a in col.adresses])
    lats = struct.pack("<%di" % n_total, *[a[4] for a in col.adresses])
    brut = b"RHADR1\0\0" + struct.pack("<II", len(entete_octets), n_total) + entete_octets + numeros + reps + lons + lats
    comprime = gzip.compress(brut, compresslevel=9)
    log(f"  index : {n_total:,} adresses, {len(rues):,} rues, {len(communes):,} communes ; "
        f"{len(brut) / 1e6:.1f} Mo bruts → {len(comprime) / 1e6:.1f} Mo gzip")

    dossier = os.path.join(DATA, "adresses")
    os.makedirs(dossier, exist_ok=True)
    for ancien in os.listdir(dossier):
        os.remove(os.path.join(dossier, ancien))
    morceaux = []
    for i in range(0, len(comprime), TAILLE_MORCEAU):
        nom = "adresses.%03d" % (i // TAILLE_MORCEAU)
        with open(os.path.join(dossier, nom), "wb") as f:
            f.write(comprime[i:i + TAILLE_MORCEAU])
        morceaux.append("data/adresses/" + nom)

    chemin_version = os.path.join(DATA, "version.json")
    version = json.load(open(chemin_version, encoding="utf-8"))
    version["paquets"]["adresses"] = {
        "nom": "Adresses Bas-Rhin et Bade", "type": "index", "taille": len(comprime), "taille_morceau": TAILLE_MORCEAU,
        "morceaux": morceaux, "sha256": hashlib.sha256(comprime).hexdigest(), "adresses": n_total, "rues": len(rues),
        "osm": entete["date"], "source": "BAN + OpenStreetMap"
    }
    json.dump(version, open(chemin_version, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # localités pour la recherche (toujours disponibles, précachées)
    localites = []
    for c in communes:
        if c[1] == "FR":
            localites.append([c[0], "FR", c[2], c[3], "commune", 0])
    for l in lieux_de:
        localites.append([l[0], "DE", round(l[1], 5), round(l[2], 5), l[3], l[4]])
    localites.sort(key=lambda x: (-x[5], x[0]))
    json.dump(localites, open(os.path.join(DATA, "communes.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    log(f"  communes.json : {len(localites):,} localités")


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--prefetch":
        # Téléchargement anticipé par un second processus (miroirs dans l'autre ordre)
        MIROIRS.reverse()
        for nom in sys.argv[2].split(","):
            poly_txt, poly = polygone_kreis(nom.strip())
            telecharger_adresses_kreis(nom.strip(), poly_txt, poly)
        log("prefetch terminé")
        return
    col = Collecte()
    log("== BAN Bas-Rhin")
    charger_ban(col)
    log("== OpenStreetMap, pays de Bade")
    lieux_de = charger_osm_bade(col)
    log("== Écriture")
    ecrire_index(col, lieux_de)


if __name__ == "__main__":
    sys.exit(main())

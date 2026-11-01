# -*- coding: utf-8 -*-
"""Emprise de la carte : Bas-Rhin + pays de Bade de Freiburg à Karlsruhe.

Récupère les limites administratives réelles (département 67 via
geo.api.gouv.fr, huit Kreise badois via Nominatim), les réunit, les élargit
d'une marge de ~2,5 km et écrit `build/emprise.geojson` (région passée à
`pmtiles extract`) ainsi qu'une version simplifiée `data/emprise.json`
affichée par l'application (limite de la carte hors ligne).

Usage : python build/emprise.py
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(RACINE, "build", "cache")
UA = "rhin-superieur-build/1.0 (carte hors ligne ; contact : cristo67000 sur GitHub)"

KREISE = [
    ("Freiburg im Breisgau", "Stadtkreis Freiburg im Breisgau"),
    ("Landkreis Breisgau-Hochschwarzwald", "Breisgau-Hochschwarzwald"),
    ("Landkreis Emmendingen", "Emmendingen"),
    ("Ortenaukreis", "Ortenaukreis"),
    ("Landkreis Rastatt", "Rastatt"),
    ("Baden-Baden", "Stadtkreis Baden-Baden"),
    ("Karlsruhe", "Stadtkreis Karlsruhe"),
    ("Landkreis Karlsruhe", "Landkreis Karlsruhe"),
]


def telecharger(url, nom_cache):
    os.makedirs(CACHE, exist_ok=True)
    chemin = os.path.join(CACHE, nom_cache)
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        texte = r.read().decode("utf-8")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(texte)
    time.sleep(1.2)  # politesse Nominatim (1 requête/s)
    return json.loads(texte)


def geometrie_bas_rhin():
    # geo.api.gouv.fr ne fournit pas de contour pour un département :
    # on passe par Nominatim comme pour les Kreise.
    return geometrie_kreis("Bas-Rhin", "Département du Bas-Rhin", ", France")


def geometrie_kreis(requete, libelle, suffixe=", Baden-Württemberg, Deutschland"):
    params = urllib.parse.urlencode({
        "q": requete + suffixe,
        "format": "geojson", "polygon_geojson": 1, "polygon_threshold": 0.002, "limit": 5,
    })
    gj = telecharger("https://nominatim.openstreetmap.org/search?" + params,
                     "limite-" + requete.replace(" ", "_") + ".geojson")
    for f in gj.get("features", []):
        p = f.get("properties", {})
        t = f["geometry"]["type"]
        if t in ("Polygon", "MultiPolygon") and p.get("type") in (
                "administrative", "county", "city") and p.get("addresstype") in (
                "county", "city", "state_district", None) or (
                t in ("Polygon", "MultiPolygon") and "boundary" in (p.get("category"), p.get("class"))):
            print(f"  {libelle:34s} ← {p.get('display_name', '')[:70]}")
            return f["geometry"]
    raise RuntimeError("aucun polygone pour " + requete + " : " +
                       json.dumps([f["properties"].get("display_name") for f in gj.get("features", [])], ensure_ascii=False))


def main():
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union

    print("Bas-Rhin…")
    formes = [shape(geometrie_bas_rhin())]
    print("Kreise badois…")
    for requete, libelle in KREISE:
        formes.append(shape(geometrie_kreis(requete, libelle)))

    union = unary_union(formes)
    # marge de ~2,5 km (0,025° ≈ 1,85 km en longitude à 48,5°, 2,8 km en latitude)
    marge = union.buffer(0.025, join_style=1).simplify(0.002)
    if marge.geom_type == "MultiPolygon":
        marge = max(marge.geoms, key=lambda g: g.area)
    # on ne garde que l'anneau extérieur : les trous n'ont pas de sens ici
    from shapely.geometry import Polygon
    marge = Polygon(marge.exterior.coords)

    def km2(g):
        import math
        kx = 111.32 * math.cos(math.radians(48.5)); ky = 110.57
        return g.area * kx * ky

    print(f"Surface des limites réunies : {km2(union):,.0f} km² ; avec marge : {km2(marge):,.0f} km²")
    b = marge.bounds
    print(f"Boîte englobante : {b[0]:.3f},{b[1]:.3f} → {b[2]:.3f},{b[3]:.3f}")

    with open(os.path.join(RACINE, "build", "emprise.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "Feature", "properties": {"nom": "Rhin supérieur — cœur"},
                   "geometry": mapping(marge)}, f)
    # version légère pour l'application (contour affiché, test « dans la carte ? »)
    leger = marge.simplify(0.01)
    with open(os.path.join(RACINE, "data", "emprise.json"), "w", encoding="utf-8") as f:
        json.dump({"bbox": [round(v, 4) for v in b],
                   "contour": [[round(x, 4), round(y, 4)] for x, y in leger.exterior.coords]}, f)
    print("Écrit : build/emprise.geojson, data/emprise.json")


if __name__ == "__main__":
    sys.exit(main())

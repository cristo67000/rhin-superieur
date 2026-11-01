# Rhin supérieur — carte hors ligne du Bas-Rhin et du pays de Bade

Application web installable (PWA) de navigation et de géolocalisation couvrant le
**Bas-Rhin** et le **pays de Bade de Freiburg à Karlsruhe**, utilisable **sans réseau**
une fois les paquets téléchargés.

**En ligne : <https://cristo67000.github.io/rhin-superieur/>** — à ouvrir dans Chrome
(Android) ou Safari (iPhone), puis « Ajouter à l'écran d'accueil » et bouton « Hors ligne »
pour télécharger les cartes.

- **Fond de carte très détaillé** (OpenStreetMap via Protomaps, zoom 15) : rues et chemins,
  bâtiments, arrêts de bus et tram, gares, rivières, forêts, frontières, villes et villages.
  Noms locaux ou en français, commerces affichables ou non, bâtiments 3D.
- **Relief** : ombrage, courbes de niveau calculées sur l'appareil, terrain 3D, altitude
  d'un point.
- **Adresses hors ligne** : Base Adresse Nationale (Bas-Rhin) + OpenStreetMap (Bade),
  numéros de maison sur la carte, adresse la plus proche d'un point.
- **Mes lieux** : adresses, lieux et coordonnées GPS (décimal, DMS, lien geo:) ajoutés par
  appui long, depuis la position ou par saisie ; catégories, notes, import/export
  GeoJSON, GPX, CSV.
- **Navigation** : position et cap (boussole), carte orientée, guidage à vol d'oiseau,
  itinéraires voiture/vélo/piéton calculés en ligne (Valhalla, OSRM) puis **enregistrés pour
  le hors ligne**, suivi pas à pas, enregistrement de traces GPX.

Tout reste sur l'appareil : aucun compte, aucune télémétrie.

## Paquets téléchargeables (bouton « Hors ligne »)

| Paquet | Poids | Contenu |
|---|---|---|
| Fond de carte | ≈ 250 Mo | tuiles vectorielles zoom 0 → 15 + Europe dézoomée |
| Relief | ≈ 55 Mo | altitudes (EU-DEM 25 m) zoom 0 → 13 |
| Adresses | ≈ 6 Mo | 843 897 adresses, 52 824 rues, 1 070 communes |

## Développement

Aucune compilation : fichiers statiques. Serveur local avec requêtes Range (indispensable
pour PMTiles) :

```bash
python build/serveur.py 8160
```

Reconstruction des données (Python 3.11, `shapely`, `numpy`, `Pillow`, `osmium`,
`build/pmtiles.exe` à télécharger depuis les versions de go-pmtiles, et les extraits
Geofabrik `freiburg-regbez` et `karlsruhe-regbez` dans `build/cache/pbf/`) :

```bash
python build/emprise.py      # limites administratives → emprise
python build/tuiles.py       # fond Protomaps + contexte Europe
python build/relief.py       # tuiles d'altitude
python build/adresses.py     # index d'adresses
python build/icones.py && python build/manifeste.py
```

Voir [ARCHITECTURE.md](ARCHITECTURE.md) pour les choix techniques et les pièges rencontrés.

## Données et licences

- Fond de carte : © les contributeurs [OpenStreetMap](https://www.openstreetmap.org/copyright)
  (ODbL), tuiles [Protomaps](https://protomaps.com).
- Relief : Terrain Tiles (Mapzen/AWS), EU-DEM © Union européenne, Copernicus.
- Adresses : [Base Adresse Nationale](https://adresse.data.gouv.fr) (licence ouverte) et
  OpenStreetMap (ODbL).
- Itinéraires : serveurs publics [Valhalla](https://valhalla.openstreetmap.de) (FOSSGIS) et
  [OSRM](https://project-osrm.org). Recherche en ligne : [Photon](https://photon.komoot.io).
- Polices Noto Sans (OFL), MapLibre GL JS (BSD), pmtiles.js (BSD), @protomaps/basemaps (BSD).

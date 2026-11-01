# Rhin supérieur — Architecture de l'application

Carte de navigation et de géolocalisation hors ligne du **Bas-Rhin** et du **pays de Bade
de Freiburg à Karlsruhe** (scénario « C » retenu le 2026-11-01 : fond vectoriel au zoom 15,
relief fin, adresses et numéros, itinéraires en ligne mémorisés). PWA sans build, dans la
lignée de `strasbourg-eurometropole` (MapLibre GL + PMTiles) dont elle reprend le socle.

Tout reste sur l'appareil : aucun compte, aucune télémétrie ; les seuls accès réseau
facultatifs sont le téléchargement des paquets, la recherche en ligne de secours (Photon)
et le calcul d'itinéraires (Valhalla/OSRM publics).

## 1. Emprise et données

| Paquet | Contenu | Poids | Fabrication |
|---|---|---|---|
| `fond` | Fond vectoriel Protomaps (OpenStreetMap) zoom 0 → 15 sur l'emprise | 243 Mo, 6 morceaux | `build/tuiles.py` (`pmtiles extract --region`) |
| `contexte` | Europe zoom 0 → 6, pour le dézoom | 6 Mo | idem |
| `relief` | Altitudes Terrarium (EU-DEM 25 m) zoom 0 → 13, WebP sans perte, précision 25 cm | 55 Mo, 2 morceaux | `build/relief.py` |
| `adresses` | Index BAN (Bas-Rhin) + OSM (Bade) : rues, numéros, communes | ~20 Mo | `build/adresses.py` |

L'emprise (`build/emprise.py` → `build/emprise.geojson`, `data/emprise.json`) est l'union
des limites réelles du département 67 et des huit Kreise badois (Stadtkreis Freiburg,
Breisgau-Hochschwarzwald, Emmendingen, Ortenaukreis, Rastatt, Baden-Baden, Stadtkreis
Karlsruhe, Landkreis Karlsruhe) récupérées sur Nominatim, élargie de 2,5 km : 12 770 km².

Chaque paquet est **découpé en morceaux de 48 Mo** (`data/<paquet>/<paquet>.NNN`) : GitHub
refuse les fichiers > 100 Mo. `data/version.json` décrit les paquets (taille, morceaux,
sha256, date OSM) ; `data/precache.json` (`build/manifeste.py`) liste l'app shell.

## 2. Lecture des données : `stockage.js`

Une archive PMTiles se lit par plages d'octets. `Stockage.lire(cle, debut, longueur)`
répartit la plage sur les morceaux et lit :

- **hors ligne** : fichiers de l'OPFS (Origin Private File System), écrits par le worker
  `telechargeur.js` (`createSyncAccessHandle`, reprise au byte près après interruption,
  manifeste écrit en dernier) et lus par `File.slice()` ;
- **sinon** : requêtes HTTP `Range` sur les morceaux publiés (GitHub Pages les sert).

Le Cache Storage est évité pour les gros fichiers (il ne sert pas une plage sans recharger
l'entrée entière — piège de Strasbourg). `Stockage.sourcePmtiles(cle)` fournit à pmtiles.js
un objet `{ getKey, getBytes }` ; `carte.js` enregistre le protocole `rhin://<paquet>/{z}/{x}/{y}`
qui route le zoom ≤ 6 vers `contexte` et le reste vers `fond` (repli sur `fond`).

## 3. Modules (ordre de chargement)

`panneau.js` (volet latéral, messages, constructeurs d'interface) → `stockage.js` →
`carte.js` (style Protomaps clair/sombre, réglages persistants, protocole, emprise) →
`recherche.js` (coordonnées GPS en décimal/DMS/geo:, agrégation des fournisseurs par score)
→ `navigation.js` (position, cap boussole, suivi/orientation, guidage à vol d'oiseau, traces
GPX) → `adresses.js` → `relief.js` (+ `courbes-worker.js`) → `lieux.js` → `itineraires.js`
→ `pwa.js` (service worker, panneau Hors ligne).

Chaque module pose ses sources et couches via `Carte.surStyle(fn)` : `fn` est rejouée à
chaque reconstruction du style (thème, langue), donc idempotente.

### Adresses (`adresses.js`)
Paquet binaire gzippé (`RHADR1`, en-tête JSON + 4 tableaux alignés : numéro u16, suffixe u16,
lon/lat i32 en millionièmes), décompressé en mémoire au premier usage. Recherche par mots
(abréviations rue/str./av…), numéro au début (France) ou à la fin (Allemagne), numéro le plus
proche si absent ; géocodage inverse par grille 0,01° ; numéros de maison dessinés dans une
source GeoJSON à partir du zoom 17. Localités (`data/communes.json`) toujours disponibles.
Secours en ligne : Photon (komoot), limité à l'emprise, désactivable.

### Relief (`relief.js`)
Source `raster-dem` Terrarium → ombrage MapLibre (sous l'eau et les routes) et terrain 3D
optionnel. Courbes de niveau calculées **sur l'appareil** : le protocole `courbes://{z}/{x}/{y}`
envoie au worker les tuiles d'altitude parente et voisines ; échantillonnage bilinéaire
257 × 257, marching squares, chaînage, encodage MVT écrit à la main (20 m, 10 m à fort zoom).
`Relief.altitude(lon, lat)` lit le pixel Terrarium.

### Itinéraires (`itineraires.js`)
Valhalla public (FOSSGIS, instructions en français ; voiture, vélo, piéton), repli OSRM
(voiture). Tracé, étapes, suivi guidé (prochaine manœuvre, distance restante, hors itinéraire),
enregistrement IndexedDB pour rejouer sans réseau, export GPX.

## 4. Recette

Le volet Navigateur de l'app de bureau ne composite pas quand il est masqué : la recette
visuelle passe par Chrome headless piloté en CDP (`scratchpad/recette/cdp.mjs` + scénarios),
géolocalisation émulée, captures bureau et téléphone. Serveur de développement :
`python build/serveur.py 8160` (requêtes Range).

## 5. Enseignements techniques

- `isStyleLoaded()` retombe à faux dès qu'une source GeoJSON d'un module charge : un module
  enregistré à ce moment attendrait un `styledata` qui ne vient pas. `Carte.surStyle` teste
  la présence des couches du style (`getStyle().layers`) et appelle aussitôt.
- `fitBounds` attend sud-ouest puis nord-est : deux points quelconques dans l'ordre inverse
  donnent des limites qui font le tour du monde (zoom 0).
- Un `[hidden]` HTML est annulé par tout `display:` en CSS : règle globale
  `[hidden] { display: none !important; }`.
- Protomaps v4 : pas de numéros de maison ni de couche transit dédiée ; `lang` inconnu (`xx`)
  donne les noms locaux (`coalesce(name:xx, name)`), les pays restent forcés en français.
- Terrarium : quantifier le canal bleu (1/256 m) à 64 près divise le poids par trois sans
  effet visible ; WebP sans perte gagne encore un tiers (96 Ko → 19 Ko par tuile).
- Overpass en sortie CSV (`out center`) pèse dix fois moins que le JSON pour les adresses.

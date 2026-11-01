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
| `adresses` | Index BAN (Bas-Rhin, 339 090 adresses) + OSM (Bade, 504 807) : 843 897 adresses, 52 824 rues, 1 070 communes | 5,7 Mo gzip (14 Mo bruts) | `build/adresses.py` |

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
  manifeste écrit en dernier, marqueur `en-cours.json` pendant le téléchargement) et lus par `File.slice()` ;
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

### Mise à jour de l'application (`miseajour.js`, `sw.js`)
Modèle repris de wortschatz : le service worker n'appelle pas `skipWaiting()` à
l'installation ; la version suivante attend, un bandeau l'annonce, le clic « Mettre à jour »
envoie `passer-devant` puis recharge ; revérification au retour à l'écran (15 min) et bouton
« Rechercher une mise à jour » dans les Réglages. La version active se demande au worker par
`MessageChannel`.

## 4. Recette

Le volet Navigateur de l'app de bureau ne composite pas quand il est masqué : la recette
visuelle passe par Chrome headless piloté en CDP (`scratchpad/recette/cdp.mjs` + scénarios),
géolocalisation émulée, captures bureau et téléphone. Serveur de développement :
`python build/serveur.py 8160` (requêtes Range).

Épreuve hors ligne de bout en bout (2026-11-01, `scenario-horsligne.mjs`) : serveur dédié,
installation des trois paquets dans l'OPFS, arrêt du serveur, rechargement → application
servie par le service worker, 1 822 entités rendues, 1 237 courbes, ombrage visible.

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
- Overpass en sortie CSV (`out center`) pèse dix fois moins que le JSON pour les adresses —
  mais les serveurs publics rejettent un Kreis entier (502/504) et restent lents même par
  cellules de 0,2°. **Retenu : les extraits PBF de Geofabrik lus par pyosmium**
  (`charger_osm_bade_pbf`, deux fichiers de ~160 Mo, deux minutes) ; Overpass n'est plus
  qu'un repli si les PBF manquent dans `build/cache/pbf/`.
- Recherche d'adresses : le numéro peut être devant (France) ou au milieu (Allemagne), un
  nombre précédé d'un article appartient au nom (« rue du 22 Novembre ») ; si rien ne
  correspond, réessayer sans le type de voie puis sans la commune (« rue des Vosges
  Strasbourg » → avenue des Vosges). Photon public : une requête toutes les 1,2 s, sinon
  429 sans en-tête CORS ; les résultats locaux s'affichent sans l'attendre.
- Les Releases GitHub ne renvoient pas d'en-tête CORS : les données vivent dans le dépôt
  Pages, en morceaux de 48 Mo.
- Le navigateur ne réinstalle un service worker que si le script `sw.js` a changé d'un octet :
  un nouveau `precache.json` seul n'est jamais relu, et les appareils installés ne voyaient
  jamais la version suivante (constaté sur Soest, 2026-11-01). `build/manifeste.py` réécrit
  donc la ligne `const BUILD = '…';` de `sw.js` à chaque build ; `install` s'en sert aussi de
  repli si `precache.json` n'a pas de champ `build`.
- Chrome arrête un service worker inactif après quelques dizaines de secondes, y compris
  celui qui attend le clic du bandeau : relancé pour `skipWaiting`, son `APP_CACHE` est
  retombé à `'initial'` et l'`activate` d'origine effaçait **tous** les caches, le neuf
  compris (constaté ici : il ne restait que `rhin-app-initial`, vide, plus rien hors ligne).
  `activate` passe donc d'abord par `cacheActuel()`, qui retrouve `PREFIXE + BUILD`.
- **Mise à jour d'un paquet : la reprise ne doit pas réutiliser les morceaux d'une autre
  version** (défaut trouvé sur Soest le 2026-11-01, corrigé ici à l'identique).
  `telechargeur.js` reprenait tout morceau déjà présent de la bonne taille ; or les morceaux
  de 48 Mo d'une nouvelle version ont exactement la même taille que les anciens : l'ancienne
  archive restait en place sous un manifeste neuf. Désormais un marqueur `en-cours.json`
  (sha256 visé) est écrit avant le premier octet : un morceau n'est réutilisé que si le
  marqueur, ou le manifeste complet, porte le même sha256 ; sinon le dossier est vidé.
  Vérifié ici en remplaçant le paquet Adresses par du bruit sous un faux sha256 (retéléchargé
  entièrement, en-tête gzip retrouvé, marqueur effacé) et en le tronquant à moitié sous le bon
  sha256 (reprise par `Range`, somme de contrôle conforme).

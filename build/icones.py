# -*- coding: utf-8 -*-
"""Icônes PWA (icons/icon-*.png) et image d'aperçu pour le partage.

Motif : le Rhin, ruban clair qui serpente du bas vers le haut sur fond
bleu-vert (couleur d'accent #0e7490), et un repère orange (vos lieux) sur la
rive. Dessiné en polygones avec Pillow, sans photo ni police : zéro build.
"""
import math
import pathlib
from PIL import Image, ImageDraw

RACINE = pathlib.Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "icons"
FOND = (14, 116, 144, 255)
FOND_SOMBRE = (9, 84, 105, 255)
EAU = (224, 242, 247, 255)
ORANGE = (234, 88, 12, 255)
BLANC = (255, 255, 255, 255)


def riviere(dessin, taille, marge, largeur):
    """Ruban sinueux : deux courbes décalées autour d'une sinusoïde."""
    points_g, points_d = [], []
    n = 60
    for i in range(n + 1):
        t = i / n
        y = taille - marge - t * (taille - 2 * marge)
        x = taille * 0.5 + math.sin(t * math.pi * 1.6 - 0.4) * taille * 0.17
        # tangente pour décaler perpendiculairement
        dx = math.cos(t * math.pi * 1.6 - 0.4) * taille * 0.17 * math.pi * 1.6 / (taille - 2 * marge)
        norme = math.hypot(1, dx)
        nx, ny = 1 / norme, dx / norme
        points_g.append((x - nx * largeur / 2, y - ny * largeur / 2))
        points_d.append((x + nx * largeur / 2, y + ny * largeur / 2))
    dessin.polygon(points_g + points_d[::-1], fill=EAU)


def repere(dessin, cx, cy, r):
    """Goutte de repère : cercle + pointe, disque blanc au centre."""
    dessin.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ORANGE)
    dessin.polygon([(cx - r * 0.72, cy + r * 0.68), (cx + r * 0.72, cy + r * 0.68), (cx, cy + r * 1.9)], fill=ORANGE)
    dessin.ellipse([cx - r * 0.42, cy - r * 0.42, cx + r * 0.42, cy + r * 0.42], fill=BLANC)


def image(taille, marge_ratio, fond=FOND, rayon_coins=None):
    img = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rayon_coins:
        d.rounded_rectangle([0, 0, taille - 1, taille - 1], radius=rayon_coins, fill=fond)
    else:
        d.rectangle([0, 0, taille, taille], fill=fond)
    marge = taille * marge_ratio
    riviere(d, taille, marge * 0.6, taille * 0.13)
    repere(d, taille * 0.70, taille * 0.40, taille * 0.11)
    return img


def apercu():
    """Image 1200×630 pour l'aperçu de lien (og:image)."""
    larg, haut = 1200, 630
    img = Image.new("RGBA", (larg, haut), FOND)
    d = ImageDraw.Draw(img)
    # bande fluviale horizontale
    pts_h, pts_b = [], []
    for i in range(121):
        t = i / 120
        x = t * larg
        y = haut * 0.55 + math.sin(t * math.pi * 2.2) * haut * 0.14
        pts_h.append((x, y - 48))
        pts_b.append((x, y + 48))
    d.polygon(pts_h + pts_b[::-1], fill=EAU)
    for cx, cy in [(300, 230), (860, 180), (640, 470)]:
        repere(d, cx, cy, 34)
    return img


def main():
    DOSSIER.mkdir(exist_ok=True)
    image(192, 0.16, rayon_coins=38).save(DOSSIER / "icon-192.png")
    image(512, 0.16, rayon_coins=100).save(DOSSIER / "icon-512.png")
    image(512, 0.28).save(DOSSIER / "icon-maskable-512.png")   # zone sûre : marge généreuse
    apercu().convert("RGB").save(DOSSIER / "apercu-1200x630.png", optimize=True)
    print("Icônes écrites dans", DOSSIER)


if __name__ == "__main__":
    main()

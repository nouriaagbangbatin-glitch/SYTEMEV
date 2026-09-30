#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calibrer_recadrage.py
======================
Petit outil pour trouver/ajuster les 4 valeurs de recadrage
(RECADRAGE_X, RECADRAGE_Y, RECADRAGE_LARGEUR, RECADRAGE_HAUTEUR) utilisées
dans serveur.py, SANS avoir à deviner à l'œil dans un logiciel de dessin.

PRINCIPE :
  1. Prenez une photo avec la caméra déjà installée en position finale
     (celle qui sera utilisée en production), et mettez-la dans ce dossier.
  2. Lancez ce script sur cette photo :
         python calibrer_recadrage.py photo.jpg
  3. Le script détecte automatiquement le rectangle blanc le plus probable
     (intérieur du cadre) et enregistre une image "apercu_recadrage.jpg"
     avec le rectangle dessiné dessus, + affiche les 4 valeurs à copier
     dans serveur.py.
  4. Ouvrez "apercu_recadrage.jpg" pour vérifier que le rectangle correspond
     bien à l'intérieur blanc du cadre (sans bois, sans fond). Si besoin,
     ajustez à la main avec les options --x --y --largeur --hauteur (voir
     ci-dessous) jusqu'à ce que ce soit parfait, puis reportez les valeurs
     finales dans serveur.py (RECADRAGE_X, RECADRAGE_Y, RECADRAGE_LARGEUR,
     RECADRAGE_HAUTEUR).

EXEMPLES :
  Détection automatique :
      python calibrer_recadrage.py photo.jpg

  Ajustement manuel (pour affiner après une première détection) :
      python calibrer_recadrage.py photo.jpg --x 140 --y 35 --largeur 390 --hauteur 520
"""

import argparse

import cv2
import numpy as np


def detecter_zone_blanche(img, seuil=150):
    """Détecte automatiquement le plus grand rectangle clair (le tissu à
    l'intérieur du cadre) et retourne (x, y, largeur, hauteur)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, masque = cv2.threshold(gray, seuil, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(masque, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("Aucune zone claire détectée -- essayez --seuil plus bas (ex: --seuil 120)")
    plus_grand = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(plus_grand)
    return x, y, w, h


def main():
    parser = argparse.ArgumentParser(description="Calibre les 4 valeurs de recadrage fixe.")
    parser.add_argument("image", help="Photo de test (prise avec la caméra en position finale)")
    parser.add_argument("--x", type=int, help="Forcer manuellement la position X (colonne)")
    parser.add_argument("--y", type=int, help="Forcer manuellement la position Y (ligne)")
    parser.add_argument("--largeur", type=int, help="Forcer manuellement la largeur")
    parser.add_argument("--hauteur", type=int, help="Forcer manuellement la hauteur")
    parser.add_argument("--seuil", type=int, default=150,
                         help="Seuil de luminosité pour la détection auto (0-255, défaut 150)")
    parser.add_argument("--sortie", default="apercu_recadrage.jpg",
                         help="Nom du fichier aperçu à générer (défaut apercu_recadrage.jpg)")
    args = parser.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        raise SystemExit(f"Impossible de lire l'image : {args.image}")

    if None in (args.x, args.y, args.largeur, args.hauteur):
        x, y, w, h = detecter_zone_blanche(img, seuil=args.seuil)
    else:
        x, y, w, h = args.x, args.y, args.largeur, args.hauteur

    # Valeurs forcées à la main : elles remplacent celles de la détection auto,
    # champ par champ, si fournies.
    if args.x is not None:
        x = args.x
    if args.y is not None:
        y = args.y
    if args.largeur is not None:
        w = args.largeur
    if args.hauteur is not None:
        h = args.hauteur

    apercu = img.copy()
    cv2.rectangle(apercu, (x, y), (x + w, y + h), (0, 0, 255), 3)
    cv2.imwrite(args.sortie, apercu)

    print(f"Image source : {img.shape[1]}x{img.shape[0]} px")
    print(f"Rectangle proposé : x={x}, y={y}, largeur={w}, hauteur={h}")
    print(f"Aperçu enregistré dans : {args.sortie} -- ouvrez-le pour vérifier.")
    print()
    print("Si le rectangle est bon, copiez ces 4 lignes dans serveur.py :")
    print(f"  RECADRAGE_X = {x}")
    print(f"  RECADRAGE_Y = {y}")
    print(f"  RECADRAGE_LARGEUR = {w}")
    print(f"  RECADRAGE_HAUTEUR = {h}")
    print()
    print("Si le rectangle n'est pas bon, relancez avec --x --y --largeur --hauteur")
    print("pour ajuster à la main, par exemple :")
    print(f"  python calibrer_recadrage.py {args.image} --x {x} --y {y} "
          f"--largeur {w} --hauteur {h}")


if __name__ == "__main__":
    main()

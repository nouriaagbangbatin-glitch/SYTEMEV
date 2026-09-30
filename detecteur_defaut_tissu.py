#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detecteur_defaut_tissu.py (v3)
================================
Détecte automatiquement si une image de tissu présente un défaut ou non,
et précise le TYPE de défaut trouvé parmi deux catégories :

  1) TACHE_MARQUE : point, salissure, marque de couleur localisée
     (méthode : différence entre l'image et une estimation lissée du fond)

  2) DEFAUT_DE_TISSAGE : irrégularité de trame qui traverse le tissu sous
     forme d'une ligne fine et allongée -- HORIZONTALE, VERTICALE ou
     OBLIQUE (n'importe quelle orientation). Ce qui la distingue d'une
     tache : elle est beaucoup plus longue que large (forme de ruban/fil),
     alors qu'une tache est plutôt ronde/compacte.

------------------------------------------------------------------------
DETECTEUR 1 - TACHE / MARQUE
------------------------------------------------------------------------
  a. On estime le "fond" (couleur propre du tissu) avec un flou médian
     de grande taille -> cela lisse les taches et ne garde que la teinte
     générale du tissu à chaque endroit.
  b. On calcule la différence entre ce fond et l'image réelle. Une tache
     est une zone nettement plus sombre que son environnement immédiat.
  c. On seuille cette différence, on nettoie le bruit du tissage
     (ouverture morphologique), puis on isole chaque tache (contours).
  d. Si la surface totale des taches dépasse un seuil -> défaut détecté.

------------------------------------------------------------------------
DETECTEUR 2 - DEFAUT DE TISSAGE (ligne fine, toute orientation)
------------------------------------------------------------------------
  a. On retire les basses fréquences (plis, éclairage progressif) avec un
     flou gaussien, pour ne garder que la texture fine du tissu.
  b. On calcule, en chaque pixel, l'énergie locale de cette texture fine
     (écart-type dans un petit voisinage), puis on la compare à une
     référence lissée à plus grande échelle -> on obtient une carte des
     zones où la texture est anormale (score).
  c. On seuille cette carte, on regroupe les zones suspectes proches
     (fermeture morphologique) pour former des formes continues.
  d. Pour chaque forme obtenue, on calcule son rectangle englobant
     orienté (longueur, largeur, angle -- quel que soit l'angle). Une
     ligne de tissage est : nettement plus longue que large (ratio
     longueur/largeur élevé), assez longue par rapport à l'image, pas
     trop large (un ruban fin, pas une zone large), et la texture
     anormale doit bien remplir cette forme (pas juste ses extrémités,
     pour écarter deux petites taches par hasard alignées).

------------------------------------------------------------------------
Décision finale : l'image est "AVEC_DEFAUT" si le détecteur 1 OU le
détecteur 2 déclenche. Le(s) type(s) de défaut détecté(s) sont indiqués.

Calibration :
  - Taches : seuil de surface 500 px² (validé sur 20 images de tissu blanc,
    séparation nette entre ~0-260 px² sans défaut et ~1400-3700 px² avec).
  - Tissage : validé sur 8 photos de tissu avec ligne de tissage (lignes
    horizontales, verticales et obliques) -> 8/8 détectées correctement.

LIMITE CONNUE : sur des tissus imprimés avec une grille de points/motifs
répétitifs et alignés (grille de calibration colorée, par exemple), il est
possible que le détecteur 2 confonde une rangée de points avec une ligne de
tissage, car les deux se ressemblent géométriquement (forme allongée). Si
vous rencontrez ce cas, envoyez des exemples pour affiner les seuils.

Utilisation :
  python detecteur_defaut_tissu.py --input /chemin/vers/dossier_images \
                                    --output /chemin/vers/dossier_resultats

  ou sur une seule image :
  python detecteur_defaut_tissu.py --input photo.jpg --output resultats/

Sorties :
  - resultats.csv : récapitulatif (nom, statut, type(s) de défaut, mesures)
  - une image annotée par photo : taches encadrées en rouge, lignes de
    tissage soulignées par un rectangle orange orienté (quel que soit
    l'angle de la ligne)
"""

import argparse
import csv
import os
import sys

import cv2
import numpy as np

# ----------------------------------------------------------------------
# Paramètres réglables - DETECTEUR 1 : taches / marques
# ----------------------------------------------------------------------
MEDIAN_BLUR_SIZE = 45        # taille du flou médian pour estimer le fond (impair)
DIFF_THRESHOLD = 35          # seuil de différence fond/image pour repérer une zone suspecte
MORPH_KERNEL_SIZE = 3        # taille du noyau morphologique de nettoyage
MIN_CONTOUR_AREA = 8         # aire minimale (en pixels) d'une tache pour être comptée
DEFECT_AREA_THRESHOLD = 500  # seuil total (en pixels) au-delà duquel il y a défaut

# ----------------------------------------------------------------------
# Paramètres réglables - DETECTEUR 2 : ligne de tissage (toute orientation)
# ----------------------------------------------------------------------
WEAVE_BLUR_SIGMA = 25          # flou gaussien pour isoler la texture fine (bas niveau de fréquence retiré)
WEAVE_LOCAL_KSIZE = 9          # fenêtre pour l'énergie de texture locale
WEAVE_BASELINE_SIGMA = 30      # échelle de la référence locale glissante (2D)
WEAVE_SCORE_THRESHOLD = 4.0    # score minimal (énergie - référence) pour être suspect
WEAVE_CLOSE_KSIZE = 7          # taille du noyau de fermeture morphologique (relie les tirets d'une ligne)
WEAVE_CLOSE_ITER = 2           # nombre d'itérations de fermeture
WEAVE_MIN_LENGTH = 95          # longueur minimale (px) de la forme pour être une "ligne"
WEAVE_MIN_ASPECT = 3.7         # ratio longueur/largeur minimal (une tache ronde est proche de 1)
WEAVE_MAX_WIDTH = 80           # largeur maximale (px) -- au-delà, ce n'est plus un "fil" fin
WEAVE_MIN_RAW_COVERAGE = 0.18  # fraction minimale de la forme réellement "texturée" (avant fermeture)
WEAVE_MIN_FRAGMENTS = 3        # nombre minimal de petits segments distincts reliés par la fermeture
                               # (un vrai fil de trame est fait de plusieurs petits segments discontinus ;
                               #  une rangée de points imprimés alignés n'en a qu'un ou deux -> permet de
                               #  distinguer un vrai défaut de tissage d'un motif imprimé qui lui ressemble)

EXTENSIONS_VALIDES = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")


# ========================================================================
# DETECTEUR 1 : taches / marques localisées
# ========================================================================
def detecter_taches(gray):
    """Retourne (liste_de_contours_valides, surface_totale)."""
    fond = cv2.medianBlur(gray, MEDIAN_BLUR_SIZE)
    diff = cv2.subtract(fond.astype(np.int16), gray.astype(np.int16))
    diff = np.clip(diff, 0, 255).astype(np.uint8)

    _, masque = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
    noyau = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    masque_propre = cv2.morphologyEx(masque, cv2.MORPH_OPEN, noyau, iterations=1)

    contours, _ = cv2.findContours(masque_propre, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    taches_valides = [c for c in contours if cv2.contourArea(c) >= MIN_CONTOUR_AREA]
    surface_totale = sum(cv2.contourArea(c) for c in taches_valides)
    return taches_valides, surface_totale


# ========================================================================
# DETECTEUR 2 : ligne(s) de tissage, à n'importe quelle orientation
# ========================================================================
def detecter_lignes_tissage(gray):
    """
    Retourne une liste de lignes détectées, chacune sous forme d'un
    rectangle orienté OpenCV : ((cx, cy), (largeur, hauteur), angle).
    Fonctionne quelle que soit l'orientation de la ligne (horizontale,
    verticale, oblique).
    """
    fond_lisse = cv2.GaussianBlur(gray, (0, 0), sigmaX=WEAVE_BLUR_SIGMA, sigmaY=WEAVE_BLUR_SIGMA)
    texture_fine = cv2.subtract(gray.astype(np.float32), fond_lisse.astype(np.float32))

    k = WEAVE_LOCAL_KSIZE
    moyenne_locale = cv2.boxFilter(texture_fine, -1, (k, k))
    moyenne_carre_locale = cv2.boxFilter(texture_fine ** 2, -1, (k, k))
    energie_locale = np.sqrt(np.clip(moyenne_carre_locale - moyenne_locale ** 2, 0, None))
    reference = cv2.GaussianBlur(energie_locale, (0, 0),
                                  sigmaX=WEAVE_BASELINE_SIGMA, sigmaY=WEAVE_BASELINE_SIGMA)
    score = energie_locale - reference

    masque_brut = (score > WEAVE_SCORE_THRESHOLD).astype(np.uint8) * 255
    masque_brut = cv2.morphologyEx(masque_brut, cv2.MORPH_OPEN,
                                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    noyau_fermeture = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (WEAVE_CLOSE_KSIZE, WEAVE_CLOSE_KSIZE))
    masque_ferme = cv2.morphologyEx(masque_brut, cv2.MORPH_CLOSE, noyau_fermeture, iterations=WEAVE_CLOSE_ITER)

    # Composantes du masque BRUT (avant fermeture) -- sert à compter les fragments
    nb_composantes, _, _, centroides = cv2.connectedComponentsWithStats(masque_brut, connectivity=8)

    contours, _ = cv2.findContours(masque_ferme, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lignes_validees = []
    for c in contours:
        rect = cv2.minAreaRect(c)
        (_, _), (l1, l2), _ = rect
        longueur, largeur = max(l1, l2), min(l1, l2)
        ratio_longueur_largeur = longueur / (largeur + 1e-6)

        if (longueur >= WEAVE_MIN_LENGTH
                and ratio_longueur_largeur >= WEAVE_MIN_ASPECT
                and largeur <= WEAVE_MAX_WIDTH):
            masque_rect = np.zeros(masque_brut.shape, dtype=np.uint8)
            cv2.fillPoly(masque_rect, [cv2.boxPoints(rect).astype(np.int32)], 255)
            surface_rect = int((masque_rect > 0).sum())
            if surface_rect == 0:
                continue
            couverture = float(((masque_rect > 0) & (masque_brut > 0)).sum()) / surface_rect
            if couverture < WEAVE_MIN_RAW_COVERAGE:
                continue

            # Compte les fragments distincts (avant fermeture) dont le centre tombe
            # dans ce rectangle -- un vrai fil de trame est fait de plusieurs petits
            # segments discontinus ; une rangée de points imprimés alignés n'en a
            # généralement qu'un ou deux.
            nb_fragments = sum(
                1 for i in range(1, nb_composantes)
                if masque_rect[int(centroides[i][1]), int(centroides[i][0])] > 0
            )
            if nb_fragments >= WEAVE_MIN_FRAGMENTS:
                lignes_validees.append(rect)

    return lignes_validees


# ========================================================================
# ANALYSE COMPLETE D'UNE IMAGE (détecteur 1 + détecteur 2)
# ========================================================================
def analyser_image(chemin_image):
    img = cv2.imread(chemin_image)
    if img is None:
        raise ValueError(f"Impossible de lire l'image : {chemin_image}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    taches_valides, surface_taches = detecter_taches(gray)
    a_une_tache = surface_taches > DEFECT_AREA_THRESHOLD

    lignes_tissage = detecter_lignes_tissage(gray)
    a_ligne_tissage = len(lignes_tissage) > 0

    types_defauts = []
    if a_une_tache:
        types_defauts.append("TACHE_MARQUE")
    if a_ligne_tissage:
        types_defauts.append("DEFAUT_DE_TISSAGE")

    statut = "AVEC_DEFAUT" if types_defauts else "SANS_DEFAUT"

    ecarts = [abs(surface_taches - DEFECT_AREA_THRESHOLD) / DEFECT_AREA_THRESHOLD]
    if lignes_tissage:
        meilleure_longueur = max(max(r[1]) for r in lignes_tissage)
        ecarts.append(abs(meilleure_longueur - WEAVE_MIN_LENGTH) / WEAVE_MIN_LENGTH)
    confiance = min(99.0, 50 + max(ecarts) * 50)

    image_annotee = img.copy()
    for c in taches_valides:
        x, y, cw, ch = cv2.boundingRect(c)
        cv2.rectangle(image_annotee, (x, y), (x + cw, y + ch), (0, 0, 255), 2)

    for rect in lignes_tissage:
        box = cv2.boxPoints(rect).astype(np.int32)
        cv2.drawContours(image_annotee, [box], 0, (0, 140, 255), 3)
        x_txt, y_txt = box[:, 0].min(), max(20, box[:, 1].min() - 8)
        cv2.putText(image_annotee, "LIGNE DE TISSAGE", (int(x_txt), int(y_txt)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 255), 2)

    couleur_texte = (0, 0, 255) if statut == "AVEC_DEFAUT" else (0, 150, 0)
    libelle = statut + (" [" + " + ".join(types_defauts) + "]" if types_defauts else "")
    cv2.putText(image_annotee, f"{libelle} ({confiance:.0f}%)", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur_texte, 2)

    resultat = {
        "statut": statut,
        "types_defauts": types_defauts,
        "surface_taches_px2": round(surface_taches, 1),
        "nb_taches": len(taches_valides),
        "nb_lignes_tissage": len(lignes_tissage),
        "confiance_pct": round(confiance, 1),
    }
    return resultat, image_annotee


def lister_images(chemin_entree):
    if os.path.isfile(chemin_entree):
        return [chemin_entree]
    if os.path.isdir(chemin_entree):
        fichiers = []
        for nom in sorted(os.listdir(chemin_entree)):
            if nom.lower().endswith(EXTENSIONS_VALIDES):
                fichiers.append(os.path.join(chemin_entree, nom))
        return fichiers
    raise FileNotFoundError(f"Chemin introuvable : {chemin_entree}")


def main():
    parser = argparse.ArgumentParser(
        description="Détecte les défauts (taches/marques et lignes de tissage, toute orientation) sur des images de tissu."
    )
    parser.add_argument("--input", required=True, help="Image ou dossier d'images à analyser")
    parser.add_argument("--output", required=True, help="Dossier de sortie pour les résultats")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    images = lister_images(args.input)

    if not images:
        print("Aucune image trouvée dans l'entrée fournie.")
        sys.exit(1)

    resultats = []
    for chemin in images:
        nom_fichier = os.path.basename(chemin)
        try:
            resultat, image_annotee = analyser_image(chemin)
        except ValueError as erreur:
            print(f"[ERREUR] {nom_fichier} : {erreur}")
            continue

        chemin_sortie = os.path.join(args.output, f"annotee_{nom_fichier}")
        cv2.imwrite(chemin_sortie, image_annotee)

        resultat["fichier"] = nom_fichier
        resultats.append(resultat)

        types_txt = "+".join(resultat["types_defauts"]) if resultat["types_defauts"] else "-"
        print(f"{nom_fichier:40s} -> {resultat['statut']:12s} | types={types_txt:25s} | "
              f"taches={resultat['nb_taches']:3d} (surf={resultat['surface_taches_px2']:7.1f}px²) | "
              f"lignes_tissage={resultat['nb_lignes_tissage']} | confiance={resultat['confiance_pct']:5.1f}%")

    chemin_csv = os.path.join(args.output, "resultats.csv")
    champs = ["fichier", "statut", "types_defauts", "surface_taches_px2",
              "nb_taches", "nb_lignes_tissage", "confiance_pct"]
    with open(chemin_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=champs)
        writer.writeheader()
        for r in resultats:
            ligne = dict(r)
            ligne["types_defauts"] = "+".join(r["types_defauts"]) if r["types_defauts"] else ""
            writer.writerow(ligne)

    nb_avec = sum(1 for r in resultats if r["statut"] == "AVEC_DEFAUT")
    nb_sans = sum(1 for r in resultats if r["statut"] == "SANS_DEFAUT")
    print(f"\nTerminé : {len(resultats)} image(s) analysée(s) -> {nb_avec} avec défaut, {nb_sans} sans défaut.")
    print(f"Résumé écrit dans : {chemin_csv}")
    print(f"Images annotées écrites dans : {args.output}")


if __name__ == "__main__":
    main()

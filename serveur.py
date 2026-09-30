#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
serveur.py
===========
Serveur HTTP qui reçoit les photos envoyées par l'ESP32-CAM (voir
esp32cam_capture_envoi.ino), les analyse avec detecteur_defaut_tissu.py,
et renvoie un résultat JSON que l'ESP32 utilise pour allumer ses LEDs.

Ce serveur expose aussi une INTERFACE WEB (tableau de bord) accessible
depuis un navigateur, pour suivre l'inspection en direct sans avoir à
lire le terminal ou ouvrir les dossiers d'images à la main.

------------------------------------------------------------------------
BOUCLE COMPLETE DU SYSTEME
------------------------------------------------------------------------
  1. L'ESP32-CAM capture une photo du tissu
  2. Il l'envoie en HTTP POST (image JPEG brute) à ce serveur, sur la
     route /analyser
  3. Ce serveur décode l'image, applique les deux détecteurs (taches et
     ligne de tissage), et renvoie un JSON de résultat
  4. L'ESP32 lit le champ "type_defaut" de ce JSON pour allumer la
     LED rouge (tache), bleue (défaut de tissage), verte (conforme),
     ou rouge+bleue (les deux), puis reprend une nouvelle capture après
     l'intervalle configuré (10 secondes par défaut côté ESP32)
  5. Le tableau de bord web (voir ci-dessous) affiche ce même résultat
     en direct, avec l'image annotée et l'historique des inspections.

------------------------------------------------------------------------
FORMAT DE REPONSE JSON (attendu tel quel par le code ESP32 fourni)
------------------------------------------------------------------------
  {
    "statut": "conforme" | "defaut",
    "type_defaut": "aucun" | "tache" | "mal_confectionne" | "tache_et_tissage",
    "pourcentage_surface_tachee": 2.45,
    "nb_taches": 3,
    "nb_lignes_tissage": 0,
    "fichier": "tissu_20260713_101530.jpg"
  }

------------------------------------------------------------------------
INTERFACE WEB (tableau de bord)
------------------------------------------------------------------------
  Une fois le serveur lancé, ouvrez dans un navigateur (sur le même PC,
  ou sur un autre appareil connecté au même réseau que le PC) :

      http://localhost:5000/dashboard        (sur le PC qui fait tourner serveur.py)
      http://192.168.4.2:5000/dashboard      (depuis un autre appareil sur le réseau ESP32)

  Le tableau de bord affiche : le résultat de la dernière photo (avec les
  mêmes indicateurs verte/rouge/bleue que les LEDs physiques), l'image
  annotée correspondante, des compteurs de session, et un historique des
  dernières inspections. Il se rafraîchit automatiquement toutes les 3
  secondes -- pas besoin de recharger la page.

------------------------------------------------------------------------
INSTALLATION ET LANCEMENT
------------------------------------------------------------------------
  1. Installer les dépendances (une seule fois) :
       pip install flask opencv-python-headless numpy

  2. Configurer le PC en IP fixe 192.168.4.2 sur le réseau WiFi créé par
     l'ESP32 ("ControleTissu_ESP32") -- voir GUIDE_INSTALLATION.md.

  3. Lancer le serveur :
       python serveur.py

     Le serveur écoute sur le port 5000, comme attendu par le code ESP32
     (const char* serverUrl = "http://192.168.4.2:5000/analyser";).

  4. Mettre l'ESP32-CAM sous tension : il crée son réseau WiFi, le PC
     doit s'y connecter, puis l'ESP32 commence à capturer et envoyer des
     photos toutes les 10 secondes.

  5. Ouvrir http://localhost:5000/dashboard dans un navigateur pour
     suivre l'inspection en direct.

Les images reçues et leurs versions annotées sont enregistrées dans les
dossiers "images_recues/" et "images_annotees/" à côté de ce script, pour
pouvoir vérifier/déboguer les décisions prises par le détecteur. Le
tableau de bord lit ces mêmes images.

L'historique des résultats est aussi conservé dans "historique.jsonl"
(une ligne JSON par photo analysée), pour que le tableau de bord retrouve
les dernières inspections même après un redémarrage du serveur.
"""

import json
import os
import sys
import time
from collections import deque
from datetime import datetime, timezone

import cv2
import numpy as np
from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from detecteur_defaut_tissu import (
    DEFECT_AREA_THRESHOLD,
    WEAVE_MIN_ASPECT,
    WEAVE_MIN_LENGTH,
    detecter_lignes_tissage,
    detecter_taches,
)

# ------------------------------------------------------------------------
# RECADRAGE FIXE DE LA ZONE UTILE (intérieur blanc du cadre en bois)
# ------------------------------------------------------------------------
# La caméra ESP32-CAM est fixe et ne bouge jamais : la position du cadre
# dans l'image est donc toujours la même d'une photo à l'autre. On peut
# donc découper un rectangle à coordonnées FIXES (en pixels) sur chaque
# image reçue, avant toute analyse, pour ne garder que la partie
# intérieure blanche du cadre (et exclure le bois du cadre + le fond).
#
# Valeurs ci-dessous estimées automatiquement à partir de la photo
# d'exemple envoyée ("image recus.jpg", 800x600) -- À VÉRIFIER/AJUSTER
# avec la caméra réellement installée (voir calibrer_recadrage.py fourni
# à côté de ce script pour ajuster ces 4 valeurs visuellement).
RECADRAGE_ACTIF = True
RECADRAGE_X = 137        # position du coin haut-gauche du rectangle (colonne)
RECADRAGE_Y = 31         # position du coin haut-gauche du rectangle (ligne)
RECADRAGE_LARGEUR = 399  # largeur du rectangle à garder
RECADRAGE_HAUTEUR = 533  # hauteur du rectangle à garder


def recadrer_image(img):
    """Découpe l'image reçue sur un rectangle à coordonnées FIXES, pour ne
    garder que l'intérieur blanc du cadre en bois. Comme la caméra ne
    bouge jamais, ces coordonnées sont valables pour toutes les photos.
    Si le rectangle configuré dépasse les bords de l'image (ex: après un
    changement de résolution côté ESP32), il est automatiquement ramené
    dans les limites de l'image plutôt que de planter."""
    if not RECADRAGE_ACTIF:
        return img

    hauteur_img, largeur_img = img.shape[:2]
    x1 = max(0, min(RECADRAGE_X, largeur_img - 1))
    y1 = max(0, min(RECADRAGE_Y, hauteur_img - 1))
    x2 = max(x1 + 1, min(RECADRAGE_X + RECADRAGE_LARGEUR, largeur_img))
    y2 = max(y1 + 1, min(RECADRAGE_Y + RECADRAGE_HAUTEUR, hauteur_img))
    return img[y1:y2, x1:x2]


def _chemin_ressource(*parties):
    """Chemin vers un fichier EMBARQUÉ dans le logiciel (ex: templates/).
    Fonctionne à la fois en script Python normal et une fois compilé en
    .exe avec PyInstaller (les fichiers embarqués sont alors extraits
    dans un dossier temporaire indiqué par sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parties)


def _chemin_donnees(*parties):
    """Chemin vers un fichier de DONNÉES (images reçues/annotées,
    historique). Ces fichiers doivent survivre aux mises à jour et rester
    à côté du programme -- donc à côté du .exe une fois compilé, jamais
    dans le dossier temporaire d'extraction de PyInstaller."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parties)


app = Flask(__name__, template_folder=_chemin_ressource("templates"))

# Intervalle de capture de l'ESP32-CAM (côté firmware .ino, pas modifiable
# ici) -- purement informatif pour l'interface, à ajuster si vous changez
# la valeur dans le code de l'ESP32.
INTERVALLE_CAPTURE_SECONDES = 10

DOSSIER_BASE = _chemin_donnees()
DOSSIER_IMAGES_RECUES = _chemin_donnees("images_recues")
DOSSIER_IMAGES_RECADREES = _chemin_donnees("images_recadrees")
DOSSIER_IMAGES_ANNOTEES = _chemin_donnees("images_annotees")
FICHIER_HISTORIQUE = _chemin_donnees("historique.jsonl")
os.makedirs(DOSSIER_IMAGES_RECUES, exist_ok=True)
os.makedirs(DOSSIER_IMAGES_RECADREES, exist_ok=True)
os.makedirs(DOSSIER_IMAGES_ANNOTEES, exist_ok=True)

# Nombre maximal d'entrées gardées en mémoire / affichées dans le tableau
# de bord. L'historique complet reste, lui, dans historique.jsonl.
TAILLE_HISTORIQUE_AFFICHE = 60

# --- Etat en mémoire, utilisé par le tableau de bord web ---
historique = deque(maxlen=TAILLE_HISTORIQUE_AFFICHE)
stats = {"total": 0, "conforme": 0, "tache": 0, "tissage": 0}


def _charger_historique_existant():
    """Recharge les dernières entrées depuis historique.jsonl au démarrage,
    pour que le tableau de bord ne reparte pas à zéro après un redémarrage."""
    if not os.path.exists(FICHIER_HISTORIQUE):
        return
    try:
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            lignes = f.readlines()
    except OSError:
        return

    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            entree = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        historique.append(entree)
        _incrementer_stats(entree["type_defaut"])


def _incrementer_stats(type_defaut):
    stats["total"] += 1
    if type_defaut == "aucun":
        stats["conforme"] += 1
    if type_defaut in ("tache", "tache_et_tissage"):
        stats["tache"] += 1
    if type_defaut in ("mal_confectionne", "tache_et_tissage"):
        stats["tissage"] += 1


def determiner_type_defaut(a_tache, a_ligne_tissage):
    """Traduit les résultats des 2 détecteurs dans le vocabulaire attendu par l'ESP32."""
    if a_tache and a_ligne_tissage:
        return "tache_et_tissage"
    if a_tache:
        return "tache"
    if a_ligne_tissage:
        return "mal_confectionne"
    return "aucun"


def construire_image_annotee(img, taches_valides, lignes_tissage, statut, type_defaut):
    image_annotee = img.copy()
    for c in taches_valides:
        x, y, w, h = cv2.boundingRect(c)
        cv2.rectangle(image_annotee, (x, y), (x + w, y + h), (0, 0, 255), 2)
    for rect in lignes_tissage:
        box = cv2.boxPoints(rect).astype(np.int32)
        cv2.drawContours(image_annotee, [box], 0, (0, 140, 255), 3)

    couleur_texte = (0, 150, 0) if type_defaut == "aucun" else (0, 0, 255)
    cv2.putText(image_annotee, f"{statut} [{type_defaut}]", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur_texte, 2)
    return image_annotee


@app.route("/analyser", methods=["POST"])
def analyser():
    donnees_image = request.get_data()
    if not donnees_image:
        return jsonify({"erreur": "Aucune image reçue dans le corps de la requête"}), 400

    tampon = np.frombuffer(donnees_image, dtype=np.uint8)
    img = cv2.imdecode(tampon, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({"erreur": "Image illisible (format non reconnu)"}), 400

    # --- Sauvegarde de l'image brute reçue (horodatée), avant recadrage ---
    horodatage = time.strftime("%Y%m%d_%H%M%S")
    horodatage_iso = datetime.now(timezone.utc).astimezone().isoformat()
    nom_fichier = f"tissu_{horodatage}.jpg"
    cv2.imwrite(os.path.join(DOSSIER_IMAGES_RECUES, nom_fichier), img)

    # --- Recadrage sur la zone fixe (intérieur blanc du cadre) ---
    # La caméra étant fixe, on découpe toujours le même rectangle, quelle
    # que soit l'image, pour ne garder que le tissu et exclure le cadre en
    # bois et le fond. Tout le reste du traitement (détecteurs, image
    # annotée, dashboard, historique) se fait ensuite sur cette image
    # recadrée, exactement comme avant sur l'image brute.
    img = recadrer_image(img)
    cv2.imwrite(os.path.join(DOSSIER_IMAGES_RECADREES, nom_fichier), img)

    # --- Analyse : les deux détecteurs du script principal ---
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    taches_valides, surface_taches = detecter_taches(gray)
    a_tache = surface_taches > DEFECT_AREA_THRESHOLD

    lignes_tissage = detecter_lignes_tissage(gray)
    a_ligne_tissage = len(lignes_tissage) > 0

    type_defaut = determiner_type_defaut(a_tache, a_ligne_tissage)
    statut = "conforme" if type_defaut == "aucun" else "defaut"

    surface_image = gray.shape[0] * gray.shape[1]
    pourcentage_surface_tachee = round(100 * surface_taches / surface_image, 2)

    # --- Sauvegarde de l'image annotée (pour vérification / debug / dashboard) ---
    image_annotee = construire_image_annotee(img, taches_valides, lignes_tissage, statut, type_defaut)
    cv2.imwrite(os.path.join(DOSSIER_IMAGES_ANNOTEES, f"annotee_{nom_fichier}"), image_annotee)

    reponse = {
        "statut": statut,
        "type_defaut": type_defaut,
        "pourcentage_surface_tachee": pourcentage_surface_tachee,
        "nb_taches": len(taches_valides),
        "nb_lignes_tissage": len(lignes_tissage),
        "fichier": nom_fichier,
    }

    # --- Mémorisation pour le tableau de bord (mémoire + fichier jsonl) ---
    entree_historique = dict(reponse)
    entree_historique["horodatage_iso"] = horodatage_iso
    historique.append(entree_historique)
    _incrementer_stats(type_defaut)
    try:
        with open(FICHIER_HISTORIQUE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entree_historique, ensure_ascii=False) + "\n")
    except OSError as erreur:
        print(f"[avertissement] impossible d'écrire dans historique.jsonl : {erreur}")

    print(f"[{horodatage}] {nom_fichier} -> {type_defaut} "
          f"(taches={len(taches_valides)}, lignes_tissage={len(lignes_tissage)})")

    return jsonify(reponse)


@app.route("/", methods=["GET"])
def accueil():
    return ("Serveur de détection de défauts de tissu -- en ligne. "
            "Envoyez une image JPEG en POST sur /analyser. "
            "Tableau de bord : /dashboard")


@app.route("/dashboard", methods=["GET"])
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/status", methods=["GET"])
def api_status():
    dernier = historique[-1] if historique else None
    age_secondes = None
    if dernier is not None:
        try:
            horodatage_dernier = datetime.fromisoformat(dernier["horodatage_iso"])
            age_secondes = (datetime.now(horodatage_dernier.tzinfo) - horodatage_dernier).total_seconds()
        except (KeyError, ValueError):
            age_secondes = None

    return jsonify({
        "dernier": dernier,
        "age_secondes_dernier": age_secondes,
        "stats": stats,
        "historique": list(historique),
        "config": {
            "seuil_surface_tache_px2": DEFECT_AREA_THRESHOLD,
            "seuil_longueur_ligne_px": WEAVE_MIN_LENGTH,
            "seuil_ratio_ligne": WEAVE_MIN_ASPECT,
            "intervalle_capture_secondes": INTERVALLE_CAPTURE_SECONDES,
        },
    })


def _repertoire_images_sur(sous_dossier):
    if sous_dossier == "recues":
        return DOSSIER_IMAGES_RECUES
    if sous_dossier == "recadrees":
        return DOSSIER_IMAGES_RECADREES
    if sous_dossier == "annotees":
        return DOSSIER_IMAGES_ANNOTEES
    abort(404)


@app.route("/images/<sous_dossier>/<path:nom_fichier>", methods=["GET"])
def servir_image(sous_dossier, nom_fichier):
    dossier = _repertoire_images_sur(sous_dossier)
    return send_from_directory(dossier, nom_fichier)


if __name__ == "__main__":
    _charger_historique_existant()
    print("Démarrage du serveur d'analyse de défauts de tissu...")
    print("En attente de connexions ESP32-CAM sur le port 5000 (route /analyser)")
    print("Tableau de bord disponible sur : http://localhost:5000/dashboard")
    app.run(host="0.0.0.0", port=5000, debug=False)

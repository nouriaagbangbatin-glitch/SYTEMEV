#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
logiciel.py
===========
Point d'entrée du LOGICIEL "Contrôle Tissu" (version application de
bureau). C'est ce fichier qu'il faut compiler en .exe (voir build_exe.bat),
et c'est ce .exe que l'utilisateur final double-clique.

Ce que fait ce fichier :
  1. Il démarre le serveur Flask (serveur.py) en arrière-plan, dans un
     thread, exactement comme "python serveur.py" le ferait.
  2. Il ouvre une VRAIE fenêtre d'application (via la bibliothèque
     pywebview, qui s'appuie sur le moteur WebView2 déjà présent sur
     Windows 10/11) pointant sur le tableau de bord.
     -> Pas de barre d'adresse, pas d'onglets, pas de menu navigateur :
        ça se comporte comme un logiciel installé, pas comme une page web.
  3. Quand l'utilisateur ferme la fenêtre, le serveur s'arrête aussi
     (tout le processus se termine proprement).

En résumé : serveur.py = le "moteur" (inchangé), logiciel.py = la
"carrosserie" qui en fait une application de bureau autonome.
"""

import threading
import time
import webbrowser

import serveur  # réutilise le serveur Flask existant tel quel

# En .exe (mode fenêtré) il n'y a pas de console : on enregistre les messages
# dans "journal.log" à côté du programme, pour pouvoir diagnostiquer un souci.
import sys
if getattr(sys, "frozen", False):
    _journal = open(serveur._chemin_donnees("journal.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = _journal
    sys.stderr = _journal

HOTE = "127.0.0.1"          # adresse utilisée par la fenêtre du logiciel
HOTE_ECOUTE = "0.0.0.0"     # le serveur doit écouter sur le réseau pour que l'ESP32-CAM
                            # (192.168.4.1) puisse envoyer ses photos à 192.168.4.2:5000
PORT = 5000
URL_TABLEAU_DE_BORD = f"http://{HOTE}:{PORT}/dashboard"


def _demarrer_serveur():
    """Lance Flask dans ce thread (bloquant), en arrière-plan de l'appli."""
    serveur._charger_historique_existant()
    serveur.app.run(host=HOTE_ECOUTE, port=PORT, debug=False, use_reloader=False)


def _attendre_serveur_pret(timeout=15):
    """Patiente jusqu'à ce que le serveur réponde, avant d'ouvrir la fenêtre
    (évite d'afficher une page d'erreur "connexion refusée" au démarrage)."""
    import urllib.request
    import urllib.error

    fin = time.time() + timeout
    while time.time() < fin:
        try:
            urllib.request.urlopen(f"http://{HOTE}:{PORT}/", timeout=1)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.3)
    return False


def main():
    thread_serveur = threading.Thread(target=_demarrer_serveur, daemon=True)
    thread_serveur.start()
    _attendre_serveur_pret()

    try:
        import webview
    except ImportError:
        # Repli : si pywebview n'est pas disponible (ex: lancement en tant
        # que simple script Python sans les dépendances desktop), on ouvre
        # le navigateur par défaut à la place -- le logiciel reste utilisable.
        print("[info] pywebview indisponible, ouverture dans le navigateur par défaut.")
        webbrowser.open(URL_TABLEAU_DE_BORD)
        thread_serveur.join()
        return

    fenetre = webview.create_window(
        "Contrôle Tissu",
        URL_TABLEAU_DE_BORD,
        width=1200,
        height=800,
        min_size=(900, 600),
    )
    webview.start()  # bloque jusqu'à la fermeture de la fenêtre


if __name__ == "__main__":
    main()

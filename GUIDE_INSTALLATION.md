# Guide d'installation — Système de contrôle de défauts sur tissu

Ce guide explique comment faire fonctionner ensemble les 3 éléments du
système :

1. **L'ESP32-CAM** : capture une photo toutes les 10 secondes et la envoie
2. **Le serveur Python** (`serveur.py`) : reçoit la photo, l'analyse, renvoie le résultat
3. **Les LEDs de l'ESP32** : s'allument selon le résultat reçu (rouge = tache, bleu = défaut de tissage, vert = conforme)

---

## 🖥️ Option A (recommandée) — Utiliser le logiciel `ControleTissu.exe`

C'est la version "vrai logiciel" : une fois compilé, il n'y a plus besoin
d'installer Python sur les PC qui l'utilisent, et il s'ouvre dans sa
propre fenêtre (pas dans un onglet de navigateur).

### A.1 — Compiler le logiciel (une seule fois, sur un PC avec Python)

1. Installez Python (une seule fois) depuis [python.org](https://www.python.org/downloads/) si ce n'est pas déjà fait — cochez bien "Add python.exe to PATH" pendant l'installation.
2. Ouvrez le dossier du projet (celui qui contient `logiciel.py`, `serveur.py`, `construire_exe.bat`...).
3. Double-cliquez sur **`construire_exe.bat`**.
   - Le script installe automatiquement les dépendances nécessaires, puis compile le logiciel.
   - Cela prend 1 à 3 minutes. Une fenêtre noire (terminal) affiche la progression.
4. À la fin, le logiciel se trouve dans : `dist\ControleTissu.exe`

### A.2 — Utiliser le logiciel (sur ce PC ou n'importe quel autre PC Windows)

1. Copiez tout le dossier `dist` (avec `ControleTissu.exe` et les dossiers `images_recues`/`images_annotees` à côté) où vous voulez — même sur une clé USB ou un autre PC Windows **sans Python installé**.
2. Double-cliquez sur `ControleTissu.exe`.
3. Une fenêtre dédiée "Contrôle Tissu" s'ouvre automatiquement avec le tableau de bord — plus besoin d'ouvrir un navigateur.
4. Pour un raccourci sur le Bureau : clic droit sur `ControleTissu.exe` → **Envoyer vers → Bureau (créer un raccourci)**.

> 💡 Les fichiers `images_recues/`, `images_annotees/` et `historique.jsonl` sont créés **à côté de `ControleTissu.exe`**, donc vos données restent avec le logiciel si vous déplacez le dossier `dist` ailleurs.

> ⚠️ La configuration réseau (IP fixe du PC sur le réseau WiFi de l'ESP32, étape B.3 ci-dessous) reste nécessaire, que vous utilisiez le `.exe` ou le mode développeur.

---

## 🐍 Option B — Mode développeur (lancer avec Python directement)

Utile si vous voulez modifier le code (ex. ajuster les seuils de détection dans `detecteur_defaut_tissu.py`) sans recompiler à chaque fois.

## Étape 1 — Installer les dépendances Python (sur le PC)

```bash
pip install flask opencv-python-headless numpy
```

## Étape 2 — Placer les fichiers

Mettez ces fichiers dans le **même dossier** sur votre PC :
- `serveur.py`
- `detecteur_defaut_tissu.py`
- le dossier `templates/`

(`serveur.py` importe les fonctions de détection directement depuis `detecteur_defaut_tissu.py` — les deux fichiers doivent donc rester ensemble.)

## Étape 3 — Configurer l'ESP32-CAM en IP fixe sur le PC

L'ESP32 crée son propre réseau WiFi (`ControleTissu_ESP32`) et attend que le
PC ait l'adresse IP **192.168.4.2** sur ce réseau (l'ESP32 lui-même est en
192.168.4.1). Il faut donc configurer cette IP fixe manuellement.

### Sur Windows
1. Connectez-vous au WiFi `ControleTissu_ESP32` (mot de passe : `controle2026`)
2. Panneau de configuration → Réseau et Internet → Centre Réseau et partage
3. Cliquez sur le réseau WiFi connecté → Propriétés
4. Sélectionnez "Protocole Internet version 4 (TCP/IPv4)" → Propriétés
5. Cochez "Utiliser l'adresse IP suivante" :
   - Adresse IP : `192.168.4.2`
   - Masque de sous-réseau : `255.255.255.0`
   - Passerelle par défaut : `192.168.4.1`
6. Validez

### Sur macOS
1. Connectez-vous au WiFi `ControleTissu_ESP32`
2. Préférences Système → Réseau → sélectionnez le WiFi → Avancé → TCP/IP
3. Configurer IPv4 : "Manuellement"
   - Adresse IP : `192.168.4.2`
   - Masque de sous-réseau : `255.255.255.0`
   - Routeur : `192.168.4.1`

### Sur Linux (exemple avec nmcli)
```bash
nmcli connection modify "ControleTissu_ESP32" ipv4.addresses 192.168.4.2/24
nmcli connection modify "ControleTissu_ESP32" ipv4.gateway 192.168.4.1
nmcli connection modify "ControleTissu_ESP32" ipv4.method manual
nmcli connection up "ControleTissu_ESP32"
```

## Étape 4 — Lancer le serveur

```bash
python serveur.py
```

### Raccourci : lancer le serveur en un clic (Windows)

Un fichier `lancer_serveur.bat` est fourni dans le dossier du projet. Il
fait exactement la même chose que la commande ci-dessus, mais en un
double-clic :
1. il se place automatiquement dans le dossier
   `C:\Users\IMMORTEL\Downloads\Desktop\mon_projet\files`,
2. il lance `python serveur.py`,
3. il ouvre tout seul le tableau de bord 3 secondes après le démarrage
   (le temps que le serveur soit prêt), dans sa **propre fenêtre dédiée**
   (mode "app" de Microsoft Edge) : pas de barre d'adresse, pas d'onglets,
   pas de menu — ça ressemble à une vraie application installée, pas à un
   onglet de navigateur perdu parmi d'autres.

Pour en faire un vrai "bouton" sur le bureau : clic droit sur
`lancer_serveur.bat` → **Envoyer vers → Bureau (créer un raccourci)**.
Vous pouvez ensuite renommer ce raccourci (ex. "Contrôle Tissu") et lui
donner une icône (clic droit → Propriétés → Changer d'icône).

> ⚠️ Il n'est pas possible de mettre ce bouton *dans* le tableau de bord
> web lui-même : la page du tableau de bord est envoyée par le serveur,
> donc le serveur doit déjà être démarré pour qu'elle s'affiche. Un
> bouton dans une page web ne peut pas, pour des raisons de sécurité du
> navigateur, lancer un programme sur votre PC — c'est pour cela que le
> lancement se fait par ce fichier `.bat` (ou son raccourci), en dehors
> du navigateur, et que le tableau de bord s'ouvre automatiquement juste
> après.

> 💡 Si la fenêtre dédiée ne s'ouvre pas (Edge introuvable, cas rare sur
> Windows 10/11), le `.bat` se rabat automatiquement sur votre navigateur
> par défaut, dans un onglet classique — le tableau de bord reste
> accessible dans tous les cas, seul l'habillage visuel change.

Vous devriez voir :
```
Démarrage du serveur d'analyse de défauts de tissu...
En attente de connexions ESP32-CAM sur le port 5000 (route /analyser)
 * Running on http://0.0.0.0:5000
```

## Étape 5 — Mettre l'ESP32-CAM sous tension

1. L'ESP32 crée son réseau WiFi et affiche son IP sur le moniteur série (192.168.4.1)
2. Toutes les 10 secondes, il capture une photo et l'envoie au serveur
3. Le serveur répond avec le résultat, et les LEDs correspondantes s'allument :
   - **Verte** : tissu conforme
   - **Rouge** : tache/marque détectée
   - **Bleue** : défaut de tissage détecté
   - **Rouge + Bleue** : les deux défauts présents

## Étape 6 — Ouvrir le tableau de bord (interface web)

Une fois le serveur lancé, ouvrez dans un navigateur :

```
http://localhost:5000/dashboard
```

(ou `http://192.168.4.2:5000/dashboard` depuis un autre appareil connecté
au même réseau WiFi que le PC).

Le tableau de bord affiche en direct :
- le résultat de la dernière photo, avec les mêmes indicateurs verte /
  rouge / bleue que les LEDs physiques de l'ESP32,
- l'image annotée correspondante,
- des compteurs de session (total analysé, conforme, tache, tissage),
- l'historique des dernières inspections avec vignettes.

Il se rafraîchit tout seul toutes les 3 secondes, pas besoin de recharger
la page. L'historique est aussi sauvegardé dans `historique.jsonl`, donc
il n'est pas perdu si vous redémarrez le serveur.

## Vérifier / déboguer

Le serveur enregistre automatiquement :
- `images_recues/` : toutes les photos reçues (horodatées)
- `images_annotees/` : les mêmes photos avec les défauts détectés encadrés

Si un résultat semble faux, regardez l'image annotée correspondante dans
`images_annotees/` pour comprendre pourquoi (tache mal détectée, ligne de
tissage ratée ou fausse alerte, etc.), et envoyez-la-moi pour affiner les
seuils si besoin.

Le terminal où tourne `serveur.py` affiche aussi une ligne par photo reçue :
```
[20260713_101530] tissu_20260713_101530.jpg -> tache (taches=3, lignes_tissage=0)
```

## Problèmes courants

| Symptôme | Cause probable |
|---|---|
| "Aucun PC connecté au point d'accès" sur le moniteur série ESP32 | Le PC n'est pas connecté au WiFi de l'ESP32, ou pas encore |
| Erreur HTTP côté ESP32 | Le serveur Python n'est pas lancé, ou l'IP fixe du PC n'est pas 192.168.4.2 |
| Le serveur ne reçoit rien | Vérifier pare-feu du PC (autoriser le port 5000 en entrée) |
| Toutes les LEDs restent éteintes | Le champ `type_defaut` renvoyé ne correspond à aucun des 4 cas attendus — regarder le moniteur série ESP32 pour le message d'erreur JSON |

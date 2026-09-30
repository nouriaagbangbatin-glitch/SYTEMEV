@echo off
setlocal
title Controle Tissu - Serveur

rem -------------------------------------------------------------------
rem Ce fichier est le "bouton" pour lancer le serveur : double-cliquez
rem dessus (ou sur un raccourci pointant vers lui) et il :
rem   1. se place dans le dossier du projet
rem   2. lance "python serveur.py"
rem   3. ouvre automatiquement le tableau de bord quelques secondes plus
rem      tard (le temps que le serveur demarre), dans sa PROPRE FENETRE
rem      dediee (mode "app" de Microsoft Edge) : pas de barre d'adresse,
rem      pas d'onglets, pas de menu -- ca ressemble a une vraie
rem      application installee, pas a un onglet de navigateur.
rem -------------------------------------------------------------------

cd /d "C:\Users\IMMORTEL\Downloads\Desktop\mon_projet\files"

echo ============================================
echo   Demarrage du serveur de controle tissu
echo ============================================
echo Dossier : %cd%
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] "python" est introuvable. Verifiez que Python est installe
    echo          et coche "Add python.exe to PATH" lors de l'installation.
    pause
    exit /b 1
)

rem Ouvre le tableau de bord 3 secondes apres le lancement (le temps que
rem le serveur Flask demarre), dans une fenetre dediee sans barre
rem d'adresse ni onglets (mode "--app" de Microsoft Edge, integre a
rem Windows 10/11 -- aucune installation supplementaire necessaire).
start "" cmd /c "timeout /t 3 >nul & (where msedge >nul 2>nul && start msedge --app=http://localhost:5000/dashboard || start http://localhost:5000/dashboard)"

python serveur.py

echo.
echo Le serveur s'est arrete.
pause

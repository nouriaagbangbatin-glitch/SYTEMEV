@echo off
REM ============================================================
REM  construire_exe.bat
REM  A lancer UNE SEULE FOIS (ou apres chaque modification du
REM  code) sur un PC Windows avec Python installe. Il produit
REM  un fichier ControleTissu.exe autonome dans le dossier "dist".
REM  Cet .exe pourra ensuite etre copie / partage sur n'importe
REM  quel PC Windows, MEME SANS PYTHON installe dessus.
REM ============================================================

cd /d "%~dp0"

echo.
echo [1/3] Installation des dependances (une seule fois)...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERREUR : l'installation des dependances a echoue.
    echo Verifiez que Python est bien installe et accessible ^(commande "python").
    pause
    exit /b 1
)

echo.
echo [2/3] Compilation en .exe avec PyInstaller...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name ControleTissu ^
    --icon icon.ico ^
    --add-data "templates;templates" ^
    logiciel.py
if errorlevel 1 (
    echo.
    echo ERREUR : la compilation a echoue. Voir le message ci-dessus.
    pause
    exit /b 1
)

echo.
echo [3/3] Copie des dossiers de donnees a cote de l'exe...
if not exist "dist\images_recues" mkdir "dist\images_recues"
if not exist "dist\images_annotees" mkdir "dist\images_annotees"

echo.
echo ============================================================
echo   TERMINE !
echo   Le logiciel se trouve dans : dist\ControleTissu.exe
echo   Vous pouvez copier tout le dossier "dist" sur un autre PC
echo   Windows : aucune installation de Python n'y est necessaire.
echo ============================================================
echo.
pause

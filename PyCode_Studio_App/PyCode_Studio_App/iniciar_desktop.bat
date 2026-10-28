@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto no_python
)
if not exist ".env" copy ".env.example" ".env" >nul
".venv\Scripts\python.exe" -m pip install -r requirements-desktop.txt
if errorlevel 1 goto install_error
".venv\Scripts\python.exe" desktop.py
if errorlevel 1 goto desktop_error
goto end
:no_python
echo Python 3 nao foi encontrado. Instale Python 3.10 ou superior e marque a opcao para adicionar ao PATH.
pause
goto end
:install_error
echo Nao foi possivel instalar dependencias da janela desktop. Tente iniciar.bat.
pause
goto end
:desktop_error
echo A janela desktop nao iniciou. Tente iniciar.bat para abrir a versao local no navegador.
pause
:end
endlocal

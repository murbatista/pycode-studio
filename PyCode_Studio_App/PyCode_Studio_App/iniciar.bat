@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente Python local...
  py -3 -m venv .venv
  if errorlevel 1 goto no_python
)
if not exist ".env" copy ".env.example" ".env" >nul
 echo Instalando/verificando dependencias do PyCode Studio...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto install_error
 echo Abrindo PyCode Studio em http://127.0.0.1:8765
start "PyCode Studio" http://127.0.0.1:8765
".venv\Scripts\python.exe" app.py
pause
goto end
:no_python
echo Python 3 nao foi encontrado. Instale Python 3.10 ou superior e marque a opcao para adicionar ao PATH.
pause
goto end
:install_error
echo Nao foi possivel instalar as dependencias. Verifique a conexao com a internet.
pause
:end
endlocal

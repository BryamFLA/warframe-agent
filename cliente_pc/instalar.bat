@echo off
REM Instala o assistente de voz no Windows.
REM Requer Python 3.12 (ou 3.11). Versoes 3.13+ nao tem pacote pronto do PyAV (usado pelo faster-whisper).
cd /d %~dp0

set PY=
py -3.12 -c "1" >nul 2>&1 && set PY=py -3.12
if not defined PY py -3.11 -c "1" >nul 2>&1 && set PY=py -3.11
if not defined PY (
  echo Python 3.12 nao encontrado.
  echo Instale em https://www.python.org/downloads/release/python-3129/ ^(Windows installer 64-bit^)
  echo e rode este arquivo de novo. Pode manter a outra versao instalada.
  goto erro
)
echo Usando %PY%

REM Recria o .venv se foi criado com outra versao do Python
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python -c "import sys;sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12)) else 1)" || rmdir /s /q .venv
)
if not exist .venv %PY% -m venv .venv || goto erro

.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install --only-binary=av -r requirements.txt || goto erro
if not exist modelos mkdir modelos
if not exist modelos\kokoro-v1.0.int8.onnx curl -L -o modelos\kokoro-v1.0.int8.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx
if not exist modelos\voices-v1.0.bin curl -L -o modelos\voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
if not exist config.json copy config.example.json config.json
echo.
echo Pronto. Edite config.json (chave da API) e rode testar.bat
pause
exit /b 0
:erro
echo Falhou. Veja a mensagem acima.
pause
exit /b 1

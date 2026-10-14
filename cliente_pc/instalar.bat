@echo off
REM Instala o assistente de voz no Windows (precisa do Python 3.11+ instalado, marcando "Add to PATH").
cd /d %~dp0
python -m venv .venv || goto erro
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt || goto erro
if not exist modelos mkdir modelos
if not exist modelos\kokoro-v1.0.int8.onnx curl -L -o modelos\kokoro-v1.0.int8.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx
if not exist modelos\voices-v1.0.bin curl -L -o modelos\voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
if not exist config.json copy config.example.json config.json
echo.
echo Pronto. Edite config.json (IP do Mac e chave) e rode iniciar.bat
pause
exit /b 0
:erro
echo Falhou. Veja a mensagem acima.
pause

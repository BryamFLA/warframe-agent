#!/usr/bin/env python3
"""Assistente de voz do Warframe para o PC de jogo (Windows).
Segure a tecla (padrão F9), fale, solte -> transcreve (faster-whisper large-v3-turbo na GPU) -> pergunta ao agente no Mac
-> fala a resposta frase a frase (Edge TTS, voz neural pt-BR; Kokoro offline como reserva) e mostra o texto numa janela por cima do jogo.
F10 mostra/esconde a janela.   Uso: python voz.py   |   python voz.py --teste   (autoteste sem microfone)"""
import os, sys, json, time, queue, threading, re, argparse
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # aviso inofensivo no Windows
import warnings; warnings.filterwarnings("ignore", module="huggingface_hub")
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
CFG = {"api_url": "http://192.168.0.10:8765", "api_key": "", "tecla_falar": "f9", "tecla_janela": "f10",
       "stt_modelo": "large-v3-turbo", "stt_device": "auto", "stt_beam": 5,
       "tts": "edge", "voz_edge": "pt-BR-AntonioNeural", "velocidade_edge": "+0%", "pausa_frase": 0.3,
       "elevenlabs_key": "", "elevenlabs_voz": "", "elevenlabs_modelo": "eleven_flash_v2_5",
       "tom_edge": "+0Hz", "efeito": "ordis", "ordis_metal": 0.35, "ordis_glitch": 0.5,
       "voz": "pm_alex", "velocidade_voz": 1.1, "salvar_gravacao": True,
       "frase_espera": True,
       "frases_espera": ["Claro, Operador. Deixe-me buscar nos arquivos.", "Um momento, Operador. Consultando os bancos de dados.",
                         "Acessando os registros do Cephalon.", "Processando. Ordis está verificando os arquivos.",
                         "Entendido, Operador. Buscando nos meus arquivos."],
       "modo": "voz", "janela_segundos": 25, "janela_alpha": 0.88, "sessao": "pc-jogo"}
if os.path.exists(os.path.join(AQUI, "config.json")):
    CFG.update(json.load(open(os.path.join(AQUI, "config.json"), encoding="utf-8")))
SR_MIC = 16000

# ---------------------------------------------------------------- ouvir (STT)
def _dlls_cuda():
    """No Windows, as DLLs do CUDA (cuBLAS/cuDNN) vêm dos pacotes pip nvidia-*; registra as pastas delas."""
    if os.name != "nt":
        return
    import site, glob
    for sp in site.getsitepackages():
        for d in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
            os.add_dll_directory(d); os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]

class Ouvido:
    def __init__(self):
        from faster_whisper import WhisperModel
        dev = CFG["stt_device"]
        if dev in ("auto", "cuda"):
            try:
                _dlls_cuda()
                self.m = WhisperModel(CFG["stt_modelo"], device="cuda", compute_type="int8_float16")
                self.m.transcribe(np.zeros(SR_MIC, dtype=np.float32), language="pt")  # força carregar cuDNN agora
                self.dev = "cuda"
            except Exception as e:
                if dev == "cuda":
                    raise
                print("[stt] GPU indisponível, usando CPU (mais lento):", str(e)[:160])
                dev = "cpu"
        if dev == "cpu":
            self.m = WhisperModel(CFG["stt_modelo"], device="cpu", compute_type="int8")
            self.dev = "cpu"
        print(f"[stt] {CFG['stt_modelo']} em {self.dev}", flush=True)
        self.prompt = ("Warframe, Tenno, Excalibur, Rhino, Orokin Cell, Argon Crystal, Cryotic, Cetus, Fortuna, Deimos, "
                       "Steel Path, Helminth, Riven, Arcane, Forma, Prime, Relíquia, Void, Lotus, Ordis, Kuva Lich, build")
    def carregar_vocabulario(self):
        try:
            import requests
            r = requests.get(CFG["api_url"].rstrip("/") + "/vocabulario", headers={"X-API-Key": CFG["api_key"]}, timeout=10)
            self.prompt = r.json()["vocabulario"][:900]
        except Exception as e:
            print("[stt] usando vocabulário padrão:", e)
    def transcrever(self, audio):
        if CFG.get("salvar_gravacao"):
            try:
                import soundfile as sf; sf.write(os.path.join(AQUI, "ultima_gravacao.wav"), audio, SR_MIC)
            except Exception:
                pass
        segs, _ = self.m.transcribe(audio, language="pt", beam_size=CFG["stt_beam"], vad_filter=True,
                                    initial_prompt=self.prompt, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segs).strip()

class Microfone:
    def __init__(self):
        import sounddevice as sd
        self.sd, self.buf, self.stream = sd, [], None
    def iniciar(self):
        self.buf = []
        self.stream = self.sd.InputStream(samplerate=SR_MIC, channels=1, dtype="float32",
                                          callback=lambda d, f, t, s: self.buf.append(d.copy()))
        self.stream.start()
    def parar(self):
        if self.stream:
            self.stream.stop(); self.stream.close(); self.stream = None
        return np.concatenate(self.buf)[:, 0] if self.buf else np.zeros(0, dtype=np.float32)

# ---------------------------------------------------------------- falar (TTS)
class Voz:
    def __init__(self):
        import sounddevice as sd
        self.sd, self.fila, self.tocar_fila, self.parar_flag = sd, queue.Queue(), queue.Queue(maxsize=3), threading.Event()
        self.kokoro, self.motor = None, CFG["tts"]
        if self.motor != "edge":
            self._carregar_kokoro()
        self.frases_prontas = []
        threading.Thread(target=self._preparar_frases, daemon=True).start()
        threading.Thread(target=self._sintetizador, daemon=True).start()
        threading.Thread(target=self._tocador, daemon=True).start()
    def _preparar_frases(self):
        """Sintetiza as frases de espera uma vez (ficam em memória: tocam na hora, sem esperar o Edge)."""
        for f in CFG.get("frases_espera") or []:
            try:
                self.frases_prontas.append(self.sintetizar(f, glitch=True))
            except Exception as e:
                print("[voz] frase de espera falhou:", e); break
    def aguardar(self):
        """Chamado logo depois da transcrição: uma frase curta de espera enquanto o Mac pensa."""
        import random
        self.parar_flag.clear()
        if CFG.get("frase_espera", True) and self.frases_prontas:
            audio, sr = random.choice(self.frases_prontas)
            self.tocar_fila.put((audio, sr, "espera"))
    def fim_espera(self):
        pass
    def _carregar_kokoro(self):
        if self.kokoro is None:
            from kokoro_onnx import Kokoro
            mdir = os.path.join(AQUI, "modelos")
            self.kokoro = Kokoro(os.path.join(mdir, "kokoro-v1.0.int8.onnx"), os.path.join(mdir, "voices-v1.0.bin"))
        return self.kokoro
    def _edge(self, texto):
        import asyncio, io, edge_tts, soundfile as sf
        async def go():
            buf = bytearray()
            async for ch in edge_tts.Communicate(texto, CFG["voz_edge"], rate=CFG["velocidade_edge"],
                                                 pitch=CFG["tom_edge"]).stream():
                if ch["type"] == "audio":
                    buf.extend(ch["data"])
            return bytes(buf)
        mp3 = asyncio.run(go())
        audio, sr = sf.read(io.BytesIO(mp3), dtype="float32")
        return audio, sr
    def _elevenlabs(self, texto):
        import requests
        r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{CFG['elevenlabs_voz']}",
                          params={"output_format": "pcm_24000"}, timeout=30,
                          headers={"xi-api-key": CFG["elevenlabs_key"]},
                          json={"text": texto, "model_id": CFG["elevenlabs_modelo"], "language_code": "pt"})
        if not r.ok:   # mostra o motivo que a ElevenLabs devolve (ex.: voz só para planos pagos, créditos esgotados)
            raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
        return np.frombuffer(r.content, dtype="<i2").astype(np.float32) / 32768, 24000
    def sintetizar(self, texto, glitch=False):
        audio, sr = None, None
        if self.motor == "elevenlabs":
            try:
                audio, sr = self._elevenlabs(texto)
            except Exception as e:
                print("[voz] ElevenLabs falhou, usando Edge:", str(e)[:160])
        if audio is None and self.motor in ("edge", "elevenlabs"):
            try:
                audio, sr = self._edge(texto)
            except Exception as e:
                print("[voz] Edge TTS falhou (sem internet?), usando Kokoro:", str(e)[:120])
        if audio is None:
            audio, sr = self._carregar_kokoro().create(texto, voice=CFG["voz"], speed=CFG["velocidade_voz"], lang="pt-br")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if CFG.get("efeito") == "ordis":
            audio = efeito_ordis(np.asarray(audio, dtype=np.float32), sr, glitch=glitch)
        return audio, sr
    def falar(self, frase):
        frase = limpar_para_fala(frase)
        if frase:
            self.fila.put(frase)
    def calar(self):
        self.parar_flag.set()
        for q in (self.fila, self.tocar_fila):
            while not q.empty():
                q.get_nowait()
        self.fim_espera()
        self.sd.stop()
    def _sintetizador(self):
        while True:
            frase = self.fila.get()
            self.parar_flag.clear()
            try:
                audio, sr = self.sintetizar(frase)
                if not self.parar_flag.is_set():
                    self.tocar_fila.put((audio, sr, "resposta"))
            except Exception as e:
                print("[voz] erro:", e)
    def _tocador(self):
        while True:
            audio, sr, tipo = self.tocar_fila.get()
            if tipo == "resposta":
                self.fim_espera()
            if not self.parar_flag.is_set():
                pausa = np.zeros(int(sr * float(CFG.get("pausa_frase", 0.3))), dtype=np.float32)   # respiro entre frases
                self.sd.play(np.concatenate([audio, pausa]), sr); self.sd.wait()

def efeito_ordis(x, sr, glitch=False, rng=np.random):
    """Voz de Cephalon "estilo Ordis" (efeito próprio, não é clone): timbre metálico, ressonância de nave,
    faixa de rádio; o gaguejo digital ("O-O-Operador") só nas frases de espera, nunca na resposta."""
    import scipy.signal as ss
    if len(x) < sr // 5:
        return x
    t = np.arange(len(x)) / sr
    m = float(CFG.get("ordis_metal", 0.35))
    # 1) metálico: ring modulation leve com duas portadoras
    ring = x * (0.6 * np.sin(2 * np.pi * 72 * t) + 0.4 * np.sin(2 * np.pi * 143 * t))
    y = (1 - m) * x + m * ring
    # 2) ressonância "de nave": comb com realimentação (~5 ms) + flanger lento
    d = int(sr * 0.005)
    y = ss.lfilter([1.0], np.r_[1.0, np.zeros(d - 1), -0.35], y)
    lfo = (0.002 + 0.0015 * np.sin(2 * np.pi * 0.4 * t)) * sr
    idx = np.clip(np.arange(len(y)) - lfo, 0, len(y) - 1)
    y = 0.75 * y + 0.25 * np.interp(idx, np.arange(len(y)), y)
    # 3) faixa de comunicador: 180 Hz – 6,5 kHz
    b, a = ss.butter(2, [180 / (sr / 2), min(6500 / (sr / 2), 0.99)], btype="band")
    y = ss.lfilter(b, a, y)
    # 4) glitch: repete o começo da frase 1-2 vezes, às vezes um "soluço" no meio
    if glitch and rng.rand() < float(CFG.get("ordis_glitch", 0.5)):
        ini = int(np.argmax(np.abs(y) > 0.05 * np.abs(y).max()))
        seg = y[ini:ini + int(sr * rng.uniform(0.07, 0.12))].copy()
        if len(seg) > 10:
            seg *= np.hanning(len(seg)) ** 0.3
            gap = np.zeros(int(sr * 0.025), dtype=y.dtype)
            y = np.concatenate([y[:ini]] + [seg, gap] * rng.randint(1, 3) + [y[ini:]])
    return (0.9 * y / (np.abs(y).max() + 1e-9)).astype(np.float32)

def limpar_para_fala(t):
    t = re.sub(r"\[\d+(,\s*\d+)*\]", "", t)            # [1], [1, 3]
    t = re.sub(r"[*_#`>|]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

# ---------------------------------------------------------------- cérebro (API no Mac)
def perguntar_stream(pergunta, on_token):
    import requests
    r = requests.post(CFG["api_url"].rstrip("/") + "/ask/stream", stream=True, timeout=180,
                      headers={"X-API-Key": CFG["api_key"]},
                      json={"pergunta": pergunta, "modo": CFG["modo"], "sessao": CFG["sessao"]})
    r.raise_for_status()
    fim = {}
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        ev = json.loads(line)
        if ev["tipo"] == "token":
            on_token(ev["texto"])
        elif ev["tipo"] == "fim":
            fim = ev
        elif ev["tipo"] == "erro":
            raise RuntimeError(ev["erro"])
    return fim

class Frases:
    """Junta tokens e entrega frases completas para a voz começar a falar cedo."""
    def __init__(self, cb):
        self.buf, self.cb = "", cb
    def add(self, t):
        self.buf += t
        while True:
            m = re.search(r"(.+?[.!?;:])(\s+|$)", self.buf, re.S)
            if not m or len(m.group(1)) < 12 and m.end() == len(self.buf):
                break
            self.cb(m.group(1)); self.buf = self.buf[m.end():]
    def fechar(self):
        if self.buf.strip():
            self.cb(self.buf)
        self.buf = ""

# ---------------------------------------------------------------- janela sobre o jogo
class Janela:
    def __init__(self):
        import tkinter as tk
        self.tk, self.ui = tk, queue.Queue()
        self.root = tk.Tk(); r = self.root
        r.overrideredirect(True); r.attributes("-topmost", True); r.attributes("-alpha", CFG["janela_alpha"])
        r.configure(bg="#11161c")
        w, h = 520, 360
        r.geometry(f"{w}x{h}+{r.winfo_screenwidth() - w - 24}+{60}")
        self.status = tk.Label(r, text="Segure " + CFG["tecla_falar"].upper() + " e fale", fg="#7fd1ff", bg="#11161c",
                               font=("Segoe UI", 10, "bold"), anchor="w")
        self.status.pack(fill="x", padx=10, pady=(8, 2))
        self.txt = tk.Text(r, wrap="word", bg="#11161c", fg="#e8edf2", insertbackground="#e8edf2", bd=0,
                           font=("Segoe UI", 11), padx=10, pady=6)
        self.txt.tag_configure("q", foreground="#ffcf6b", font=("Segoe UI", 11, "italic"))
        self.txt.tag_configure("lista", foreground="#b9c4cf", font=("Segoe UI", 9))
        self.txt.pack(fill="both", expand=True)
        for wdg in (r, self.status):                       # arrastar a janela
            wdg.bind("<ButtonPress-1>", self._ini); wdg.bind("<B1-Motion>", self._mov)
        self.visivel, self.ultimo = True, time.time()
        r.after(100, self._loop)
    def _ini(self, e): self._x, self._y = e.x, e.y
    def _mov(self, e): self.root.geometry(f"+{e.x_root - self._x}+{e.y_root - self._y}")
    def post(self, *ev): self.ui.put(ev)
    def _loop(self):
        try:
            while True:
                ev = self.ui.get_nowait(); k = ev[0]; self.ultimo = time.time()
                if k == "status": self.status.config(text=ev[1]); self._mostrar()
                elif k == "nova": self.txt.delete("1.0", "end"); self.txt.insert("end", ev[1] + "\n\n", "q"); self._mostrar()
                elif k == "token": self.txt.insert("end", ev[1]); self.txt.see("end")
                elif k == "lista": self.txt.insert("end", "\n\n" + ev[1], "lista"); self.txt.see("1.0")
                elif k == "alternar": (self._esconder() if self.visivel else self._mostrar())
        except queue.Empty:
            pass
        if self.visivel and CFG["janela_segundos"] and time.time() - self.ultimo > CFG["janela_segundos"]:
            self._esconder()
        self.root.after(100, self._loop)
    def _mostrar(self): self.root.deiconify(); self.root.attributes("-topmost", True); self.visivel = True
    def _esconder(self): self.root.withdraw(); self.visivel = False

# ---------------------------------------------------------------- orquestração
class App:
    def __init__(self):
        print("Carregando transcrição e voz...", flush=True)
        self.ouvido, self.voz, self.mic, self.jan = Ouvido(), Voz(), Microfone(), Janela()
        self.ouvido.carregar_vocabulario()
        self.gravando, self.ocupado = False, False
    def apertou(self, _=None):
        if self.gravando:
            return
        self.voz.calar()                                   # interrompe a fala anterior
        self.gravando = True; self.mic.iniciar(); self.jan.post("status", "🎙️ Ouvindo...")
    def soltou(self, _=None):
        if not self.gravando:
            return
        self.gravando = False; audio = self.mic.parar()
        if len(audio) < SR_MIC * 0.4 or self.ocupado:
            self.jan.post("status", "Segure " + CFG["tecla_falar"].upper() + " e fale"); return
        threading.Thread(target=self.processar, args=(audio,), daemon=True).start()
    def processar(self, audio):
        self.ocupado = True
        try:
            t0 = time.time(); self.jan.post("status", "📝 Transcrevendo...")
            q = self.ouvido.transcrever(audio)
            if not q:
                self.jan.post("status", "Não entendi, tente de novo"); return
            self.jan.post("nova", q); self.jan.post("status", f"🧠 Pensando... (transcrição {time.time() - t0:.1f}s)")
            self.voz.aguardar()
            fr = Frases(self.voz.falar); t1 = time.time(); prim = []
            def tok(t):
                if not prim:
                    prim.append(1); self.jan.post("status", f"🔊 Respondendo ({time.time() - t1:.1f}s)")
                self.jan.post("token", t); fr.add(t)
            fim = perguntar_stream(q, tok); fr.fechar()
            if fim.get("lista_completa"):
                self.jan.post("lista", "Lista completa:\n" + fim["lista_completa"])
            self.jan.post("status", f"✅ {time.time() - t0:.1f}s · segure {CFG['tecla_falar'].upper()} para outra pergunta")
        except Exception as e:
            self.jan.post("status", f"⚠️ Erro: {e}"); self.voz.fim_espera()
        finally:
            self.ocupado = False
    def rodar(self):
        import keyboard
        keyboard.on_press_key(CFG["tecla_falar"], self.apertou, suppress=False)
        keyboard.on_release_key(CFG["tecla_falar"], self.soltou, suppress=False)
        keyboard.add_hotkey(CFG["tecla_janela"], lambda: self.jan.post("alternar"))
        print(f"Pronto! Segure {CFG['tecla_falar'].upper()} para falar, {CFG['tecla_janela'].upper()} mostra/esconde a janela.", flush=True)
        self.jan.root.mainloop()

# ---------------------------------------------------------------- autoteste (sem microfone/teclado)
def autoteste(tocar):
    import soundfile as sf
    t = time.time(); v = Voz(); print(f"[voz] motor {CFG['tts']} carregado em {time.time() - t:.1f}s")
    frase = "Operador! Para conseguir o Rhino, derrote o Jackal em Fossa, Vênus."
    t = time.time(); audio, sr = v.sintetizar(frase); print(f"[voz] sintetizou {len(audio)/sr:.1f}s de áudio em {time.time() - t:.1f}s")
    sf.write(os.path.join(AQUI, "teste_voz.wav"), audio, sr)
    if tocar:
        v.sd.play(audio, sr); v.sd.wait()
    print("[stt] carregando Whisper (1ª vez baixa ~1,6 GB, pode levar alguns minutos)...", flush=True)
    t = time.time(); o = Ouvido(); o.carregar_vocabulario(); print(f"[stt] carregado em {time.time() - t:.1f}s")
    import scipy.signal as ss
    a16 = ss.resample_poly(audio, SR_MIC, sr).astype(np.float32)
    t = time.time(); txt = o.transcrever(a16); print(f"[stt] '{txt}' em {time.time() - t:.1f}s")
    if CFG["api_key"] and tocar:
        print("[espera] frase de espera + resposta falada...", flush=True)
        while len(v.frases_prontas) < 1:
            time.sleep(0.2)
        v.aguardar(); fr = Frases(v.falar)
        fim = perguntar_stream("o que eu posso fazer em cetus?", fr.add); fr.fechar()
        while v.fila.qsize() or v.tocar_fila.qsize():
            time.sleep(0.3)
        time.sleep(4)
    if CFG["api_key"]:
        t = time.time(); prim = []
        fim = perguntar_stream("onde consigo o rhino?", lambda x: prim.append(time.time() - t) if not prim else None)
        print(f"[api] 1º token {prim[0] if prim else -1:.1f}s, total {time.time() - t:.1f}s -> {fim.get('resposta', '')[:200]}")
    else:
        print("[api] sem api_key no config.json: pulei o teste da API")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--teste", action="store_true"); ap.add_argument("--tocar", action="store_true")
    a = ap.parse_args()
    autoteste(a.tocar) if a.teste else App().rodar()

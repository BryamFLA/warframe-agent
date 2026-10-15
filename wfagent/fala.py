"""Voz para o bot do Telegram (no Mac): transcrição (faster-whisper) e síntese (Edge TTS + efeito Ordis) em OGG/Opus.
Mesmo efeito do cliente do PC (cliente_pc/voz.py), sem o gaguejo."""
import io, re, asyncio
import numpy as np

VOZ_EDGE = "pt-BR-AntonioNeural"

def efeito_ordis(x, sr, metal=0.35):
    """Voz de Cephalon "estilo Ordis" (efeito próprio): metálico (ring mod), ressonância de nave, faixa de rádio."""
    import scipy.signal as ss
    if len(x) < sr // 5:
        return x
    t = np.arange(len(x)) / sr
    ring = x * (0.6 * np.sin(2 * np.pi * 72 * t) + 0.4 * np.sin(2 * np.pi * 143 * t))
    y = (1 - metal) * x + metal * ring
    d = int(sr * 0.005)
    y = ss.lfilter([1.0], np.r_[1.0, np.zeros(d - 1), -0.35], y)
    lfo = (0.002 + 0.0015 * np.sin(2 * np.pi * 0.4 * t)) * sr
    idx = np.clip(np.arange(len(y)) - lfo, 0, len(y) - 1)
    y = 0.75 * y + 0.25 * np.interp(idx, np.arange(len(y)), y)
    b, a = ss.butter(2, [180 / (sr / 2), min(6500 / (sr / 2), 0.99)], btype="band")
    y = ss.lfilter(b, a, y)
    return (0.9 * y / (np.abs(y).max() + 1e-9)).astype(np.float32)

def limpar_para_fala(t):
    t = re.sub(r"\[\d+(,\s*\d+)*\]", "", t)
    t = re.sub(r"[*_#`>|]", "", t)
    return re.sub(r"\s+", " ", t).strip()

def sintetizar_ogg(texto, voz=VOZ_EDGE, velocidade="+0%", efeito=True, pausa=0.3):
    """Texto -> bytes OGG/Opus (formato de mensagem de voz do Telegram). Frase a frase, com respiro entre elas."""
    import edge_tts, soundfile as sf
    frases = [f for f in re.split(r"(?<=[.!?;])\s+", limpar_para_fala(texto)) if f.strip()]
    async def uma(f):
        buf = bytearray()
        async for ch in edge_tts.Communicate(f, voz, rate=velocidade).stream():
            if ch["type"] == "audio":
                buf.extend(ch["data"])
        return bytes(buf)
    async def todas():
        return await asyncio.gather(*(uma(f) for f in frases))
    partes, sr = [], 24000
    for mp3 in asyncio.run(todas()):
        a, sr = sf.read(io.BytesIO(mp3), dtype="float32")
        a = a.mean(axis=1) if a.ndim > 1 else a
        partes += [a, np.zeros(int(sr * pausa), np.float32)]
    audio = np.concatenate(partes) if partes else np.zeros(sr // 2, np.float32)
    if efeito:
        audio = efeito_ordis(audio, sr)
    out = io.BytesIO()
    sf.write(out, audio, sr, format="OGG", subtype="OPUS")
    return out.getvalue(), len(audio) / sr

def decodificar(dados, sr=16000):
    """Bytes de áudio (OGG/Opus do Telegram, MP3, M4A...) -> numpy mono 16 kHz."""
    import soundfile as sf
    from scipy.signal import resample_poly
    try:
        a, sr0 = sf.read(io.BytesIO(dados), dtype="float32")
        a = a.mean(axis=1) if a.ndim > 1 else a
    except Exception:                       # formatos que o libsndfile não lê (ex.: M4A): PyAV
        import av
        with av.open(io.BytesIO(dados)) as c:
            rs = av.AudioResampler(format="flt", layout="mono", rate=sr)
            a = np.concatenate([f.to_ndarray().reshape(-1) for fr in c.decode(audio=0) for f in rs.resample(fr)])
        return a.astype(np.float32)
    from math import gcd
    g = gcd(sr, sr0)
    return resample_poly(a, sr // g, sr0 // g).astype(np.float32)

class Ouvido:
    """Transcrição de áudio do Telegram (OGG/Opus) no processador do Mac; carrega na 1ª mensagem de voz."""
    def __init__(self, modelo="large-v3-turbo", vocabulario=""):
        self.modelo, self.prompt, self.m = modelo, vocabulario, None
    def transcrever(self, dados):
        if self.m is None:
            from faster_whisper import WhisperModel
            self.m = WhisperModel(self.modelo, device="cpu", compute_type="int8")
        segs, _ = self.m.transcribe(decodificar(dados), language="pt", beam_size=5, vad_filter=True,
                                    initial_prompt=self.prompt or None, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segs).strip()

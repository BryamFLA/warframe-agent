#!/usr/bin/env python3
"""Bot do Telegram do agente Warframe. Roda no Mac ao lado da API e usa *long polling*:
o próprio bot busca as mensagens no Telegram, então não precisa abrir porta nem ter URL pública.

Configurar (1x):  .venv/bin/python telegram_bot.py --configurar
Rodar:            .venv/bin/python telegram_bot.py
No chat:          texto ou áudio | /nova (esquece a conversa) | /audio (resposta em áudio também p/ texto) | /id
Admin:            /liberar <id> [nome] | /remover <id> | /usuarios
"""
import os, sys, re, json, time, html, queue, getpass, argparse, threading, traceback
import requests

AQUI = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(AQUI, "cache")
CFG_FILE = os.path.join(CACHE, "telegram.json")
API = os.environ.get("WF_API_URL", "http://127.0.0.1:8765")
LIMITE_TG = 3800

def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)

# ---------------------------------------------------------------- configuração
def carregar_cfg():
    c = json.load(open(CFG_FILE, encoding="utf-8")) if os.path.exists(CFG_FILE) else {}
    c.setdefault("admins", []); c.setdefault("usuarios", {}); c.setdefault("audio_sempre", [])
    c.setdefault("voz", "pt-BR-AntonioNeural"); c.setdefault("efeito_ordis", True)
    return c

def salvar_cfg(c):
    os.makedirs(CACHE, exist_ok=True)
    tmp = CFG_FILE + ".tmp"
    json.dump(c, open(tmp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    os.replace(tmp, CFG_FILE)
    os.chmod(CFG_FILE, 0o600)

# ---------------------------------------------------------------- Telegram
class TG:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}"
        self.arq = f"https://api.telegram.org/file/bot{token}"
    def call(self, metodo, files=None, timeout=70, **p):
        if files:
            r = requests.post(f"{self.base}/{metodo}", data={k: str(v) for k, v in p.items()}, files=files, timeout=timeout)
        else:
            r = requests.post(f"{self.base}/{metodo}", json=p, timeout=timeout)
        d = r.json()
        if not d.get("ok"):
            raise RuntimeError(f"{metodo}: {d.get('description')}")
        return d["result"]
    def baixar(self, file_id):
        caminho = self.call("getFile", file_id=file_id)["file_path"]
        return requests.get(f"{self.arq}/{caminho}", timeout=60).content
    def enviar(self, chat, texto, html_ok=True):
        for parte in dividir(texto):
            try:
                extra = {"parse_mode": "HTML"} if html_ok else {}
                self.call("sendMessage", chat_id=chat, text=md_html(parte) if html_ok else parte,
                          disable_web_page_preview=True, **extra)
            except RuntimeError:          # formatação recusada: manda como texto puro
                self.call("sendMessage", chat_id=chat, text=re.sub(r"\*\*|^#+\s*", "", parte, flags=re.M))

def dividir(t, n=LIMITE_TG):
    partes = []
    while len(t) > n:
        corte = t.rfind("\n", 0, n)
        corte = corte if corte > n // 2 else n
        partes.append(t[:corte]); t = t[corte:].lstrip("\n")
    return partes + ([t] if t.strip() else [])

def md_html(t):
    """Markdown simples do agente -> HTML do Telegram."""
    t = html.escape(t, quote=False)
    t = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
    t = re.sub(r"^\s*[-*]\s+", "• ", t, flags=re.M)
    return t

def sem_citacoes(t):
    return re.sub(r"\s?\[\d+(?:[,\s]+\d+)*\]", "", t)

# ---------------------------------------------------------------- agente (API local)
class Agente:
    def __init__(self):
        self.key = open(os.path.join(CACHE, "api_key.txt")).read().strip()
    def perguntar(self, pergunta, modo, sessao, profundidade="auto", on_progresso=None):
        """Usa /ask/stream para receber o progresso do modo profundo (perguntas complexas levam alguns minutos)."""
        r = requests.post(f"{API}/ask/stream", headers={"X-API-Key": self.key}, timeout=(10, 1800), stream=True,
                          json={"pergunta": pergunta, "modo": modo, "sessao": sessao, "profundidade": profundidade})
        r.raise_for_status()
        for linha in r.iter_lines():
            if not linha:
                continue
            ev = json.loads(linha)
            if ev["tipo"] == "progresso" and on_progresso:
                try:
                    on_progresso(ev)
                except Exception as e:
                    log("progresso:", e)
            elif ev["tipo"] == "fim":
                return ev
            elif ev["tipo"] == "erro":
                raise RuntimeError(ev["erro"])
        raise RuntimeError("a API encerrou sem resposta")
    def vocabulario(self):
        try:
            return requests.get(f"{API}/vocabulario", headers={"X-API-Key": self.key}, timeout=10).json()["vocabulario"]
        except Exception:
            return ""

# ---------------------------------------------------------------- bot
AJUDA = ("Olá, Operador. Sou o assistente de Warframe.\n\n"
         "Pergunte por texto ou áudio, por exemplo:\n"
         "• onde consigo o Rhino?\n• qual a melhor build para a Saryn?\n"
         "• o que eu posso fazer em Cetus?\n• liste tudo que posso conseguir em Fortuna\n\n"
         "Perguntas amplas (\"qual a história do jogo?\", \"guia do iniciante ao endgame\") ativam o modo profundo: "
         "pesquiso em etapas, confiro cada parte e monto uma resposta longa (leva alguns minutos).\n"
         "/profundo <pergunta> força o modo profundo · /rapido <pergunta> força a resposta direta\n\n"
         "/nova esquece a conversa · /audio liga/desliga resposta em áudio · /id mostra seu ID")

class Bot:
    def __init__(self):
        self.cfg = carregar_cfg()
        if not self.cfg.get("token"):
            sys.exit("Bot não configurado. Rode: .venv/bin/python telegram_bot.py --configurar")
        if not self.cfg["admins"]:
            log("Sem administrador: a primeira pessoa que mandar mensagem vira administradora.")
        self.tg, self.ag = TG(self.cfg["token"]), Agente()
        self.fila, self.sessao_n, self.avisados = queue.Queue(), {}, set()
        self.ouvido = None

    # -- acesso
    def liberado(self, uid):
        return uid in self.cfg["admins"] or str(uid) in self.cfg["usuarios"]
    def pedir_acesso(self, msg):
        u = msg["from"]; uid = u["id"]
        self.tg.enviar(msg["chat"]["id"], f"Acesso não liberado.\nSeu ID: {uid}\nPeça ao dono do bot para liberar.", html_ok=False)
        if uid not in self.avisados:
            self.avisados.add(uid)
            nome = (u.get("first_name", "") + " " + u.get("last_name", "")).strip() + (f" (@{u['username']})" if u.get("username") else "")
            for a in self.cfg["admins"]:
                self.tg.enviar(a, f"Pedido de acesso: {nome} — ID {uid}\nPara liberar: /liberar {uid} {u.get('first_name', '')}", html_ok=False)

    # -- comandos
    def comando(self, msg, texto):
        chat, uid = msg["chat"]["id"], msg["from"]["id"]
        cmd, *args = texto.split()
        cmd = cmd.split("@")[0].lower()
        admin = uid in self.cfg["admins"]
        if cmd in ("/start", "/ajuda", "/help"):
            self.tg.enviar(chat, AJUDA, html_ok=False)
        elif cmd == "/id":
            self.tg.enviar(chat, f"Seu ID: {uid}", html_ok=False)
        elif cmd == "/nova":
            self.sessao_n[chat] = self.sessao_n.get(chat, 0) + 1
            self.tg.enviar(chat, "Conversa reiniciada.", html_ok=False)
        elif cmd == "/audio":
            s = self.cfg["audio_sempre"]
            (s.remove(chat) if chat in s else s.append(chat)); salvar_cfg(self.cfg)
            self.tg.enviar(chat, "Respostas em áudio: " + ("ligadas" if chat in s else "só quando você mandar áudio"), html_ok=False)
        elif cmd == "/liberar" and admin and args and args[0].lstrip("-").isdigit():
            self.cfg["usuarios"][args[0]] = " ".join(args[1:]) or args[0]; salvar_cfg(self.cfg)
            self.tg.enviar(chat, f"Liberado: {args[0]}", html_ok=False)
            try:
                self.tg.enviar(int(args[0]), "Seu acesso foi liberado. Mande /start.", html_ok=False)
            except Exception:
                pass
        elif cmd == "/remover" and admin and args:
            self.cfg["usuarios"].pop(args[0], None); salvar_cfg(self.cfg)
            self.tg.enviar(chat, f"Removido: {args[0]}", html_ok=False)
        elif cmd == "/usuarios" and admin:
            us = "\n".join(f"• {k} — {v}" for k, v in self.cfg["usuarios"].items()) or "(nenhum além de você)"
            self.tg.enviar(chat, "Usuários liberados:\n" + us, html_ok=False)
        else:
            self.tg.enviar(chat, "Comando desconhecido. /ajuda", html_ok=False)

    # -- perguntas (uma por vez: o Mac responde uma geração por vez)
    def digitando(self, chat, acao, parar):
        while not parar.wait(4.5):
            try:
                self.tg.call("sendChatAction", chat_id=chat, action=acao, timeout=10)
            except Exception:
                pass

    def responder(self, msg):
        chat = msg["chat"]["id"]
        audio_in = msg.get("voice") or msg.get("audio")
        parar = threading.Event()
        acao = "record_voice" if (audio_in or chat in self.cfg["audio_sempre"]) else "typing"
        try:
            self.tg.call("sendChatAction", chat_id=chat, action=acao, timeout=10)
        except Exception:
            pass
        threading.Thread(target=self.digitando, args=(chat, acao, parar), daemon=True).start()
        try:
            t0 = time.time()
            if audio_in:
                if audio_in.get("duration", 0) > 120:
                    self.tg.enviar(chat, "Áudio muito longo (máx. 2 min).", html_ok=False); return
                if self.ouvido is None:
                    from wfagent.fala import Ouvido
                    self.ouvido = Ouvido(vocabulario=self.ag.vocabulario()[:900])
                pergunta = self.ouvido.transcrever(self.tg.baixar(audio_in["file_id"]))
                if not pergunta:
                    self.tg.enviar(chat, "Não entendi o áudio, pode repetir?", html_ok=False); return
                self.tg.call("sendMessage", chat_id=chat, text=f"🎙️ {pergunta}", reply_to_message_id=msg["message_id"])
            else:
                pergunta = msg["text"]
            profundidade = "auto"
            m = re.match(r"/(profundo|rapido|rápido)(@\w+)?\s+(.*)", pergunta, re.I | re.S)
            if m:
                profundidade = "profunda" if m.group(1).lower() == "profundo" else "simples"
                pergunta = m.group(3).strip()
            status = {"id": None, "linhas": []}
            def progresso(ev):                     # modo profundo: uma mensagem de status editada a cada etapa
                status["linhas"].append(ev["texto"])
                txt = "\n".join(status["linhas"][-12:])
                if status["id"] is None:
                    status["id"] = self.tg.call("sendMessage", chat_id=chat, text=txt)["message_id"]
                else:
                    self.tg.call("editMessageText", chat_id=chat, message_id=status["id"], text=txt)
            falar = bool(audio_in) or chat in self.cfg["audio_sempre"]
            sessao = f"tg-{chat}-{self.sessao_n.get(chat, 0)}"
            r = self.ag.perguntar(pergunta, "voz" if falar else "texto", sessao, profundidade, progresso)
            if status["id"]:
                try:
                    self.tg.call("editMessageText", chat_id=chat, message_id=status["id"],
                                 text="\n".join(status["linhas"][-12:]) + f"\n✅ Pronto em {time.time() - t0:.0f}s")
                except Exception:
                    pass
            resposta = sem_citacoes(r["resposta"]).strip()
            texto = resposta + (("\n\n**Lista completa**\n" + r["lista_completa"]) if r.get("lista_completa") else "")
            self.tg.enviar(chat, texto)
            if falar and resposta:
                from wfagent.fala import sintetizar_ogg
                ogg, dur = sintetizar_ogg(resposta, voz=self.cfg["voz"], efeito=self.cfg["efeito_ordis"])
                self.tg.call("sendVoice", files={"voice": ("resposta.ogg", ogg, "audio/ogg")}, chat_id=chat, duration=int(dur) + 1)
            log(f"chat {chat}: {pergunta[:60]!r} -> {time.time() - t0:.1f}s ({r.get('rota', {}).get('intencao')})")
        except Exception as e:
            log("erro:", e); traceback.print_exc()
            self.tg.enviar(chat, "⚠️ Não consegui responder agora (o Mac pode estar ocupado ou desligado). Tente de novo.", html_ok=False)
        finally:
            parar.set()

    def trabalhador(self):
        while True:
            msg = self.fila.get()
            self.responder(msg)

    def rodar(self):
        me = self.tg.call("getMe")
        self.tg.call("deleteWebhook")
        try:
            self.tg.call("setMyCommands", commands=[
                {"command": "nova", "description": "Esquece a conversa"},
                {"command": "audio", "description": "Liga/desliga resposta em áudio"},
                {"command": "id", "description": "Mostra seu ID"},
                {"command": "ajuda", "description": "Exemplos de perguntas"}])
        except Exception:
            pass
        log(f"Bot @{me['username']} rodando. API: {API}")
        threading.Thread(target=self.trabalhador, daemon=True).start()
        offset = None
        while True:
            try:
                ups = self.tg.call("getUpdates", offset=offset, timeout=50, allowed_updates=["message"])
            except Exception as e:
                log("sem conexão com o Telegram:", e); time.sleep(5); continue
            for u in ups:
                offset = u["update_id"] + 1
                msg = u.get("message")
                if not msg or "from" not in msg:
                    continue
                try:
                    self.tratar(msg)
                except Exception as e:
                    log("erro ao tratar mensagem:", e)

    def tratar(self, msg):
        uid, chat = msg["from"]["id"], msg["chat"]["id"]
        texto = (msg.get("text") or "").strip()
        if texto.startswith("/id"):
            return self.comando(msg, texto)
        if not self.cfg["admins"]:          # 1ª mensagem depois de configurar só com o token: vira administrador
            self.cfg["admins"] = [uid]; salvar_cfg(self.cfg)
            log(f"Administrador definido: {msg['from'].get('first_name', '')} (ID {uid})")
            self.tg.enviar(chat, "✅ Você é o administrador deste bot.\n\n" + AJUDA, html_ok=False)
            return
        if not self.liberado(uid):
            return self.pedir_acesso(msg)
        if re.match(r"/(profundo|rapido|rápido)(@\w+)?\s+\S", texto, re.I):
            pass                                   # pergunta com modo forçado: vai para a fila
        elif texto.startswith("/"):
            return self.comando(msg, texto)
        if not texto and not (msg.get("voice") or msg.get("audio")):
            return self.tg.enviar(chat, "Mande uma pergunta em texto ou áudio.", html_ok=False)
        if self.fila.qsize() >= 1:
            self.tg.enviar(chat, f"⏳ Na fila ({self.fila.qsize()} pergunta(s) antes da sua).", html_ok=False)
        self.fila.put(msg)

# ---------------------------------------------------------------- configuração guiada
def configurar():
    c = carregar_cfg()
    print("1) No Telegram, fale com @BotFather -> /newbot -> copie o token.")
    token = getpass.getpass("Cole o token do bot (não aparece na tela): ").strip()
    tg = TG(token)
    try:
        me = tg.call("getMe")
    except Exception as e:
        sys.exit(f"Token inválido: {e}")
    tg.call("deleteWebhook")
    print(f"Bot encontrado: @{me['username']}")
    print(f"2) Agora mande /start para @{me['username']} no Telegram (você será o administrador). Aguardando 3 min...")
    offset, fim = None, time.time() + 180
    for u in tg.call("getUpdates", timeout=0):     # ignora mensagens antigas
        offset = u["update_id"] + 1
    while time.time() < fim:
        for u in tg.call("getUpdates", offset=offset, timeout=30):
            offset = u["update_id"] + 1
            m = u.get("message")
            if m and "from" in m:
                f = m["from"]
                c.update(token=token, admins=[f["id"]])
                salvar_cfg(c)
                tg.call("getUpdates", offset=offset, timeout=0)
                tg.call("sendMessage", chat_id=m["chat"]["id"], text="✅ Configurado. Você é o administrador deste bot.")
                print(f"Pronto! Administrador: {f.get('first_name', '')} (ID {f['id']}). Config salva em cache/telegram.json")
                return
    sys.exit("Nenhuma mensagem recebida. Rode --configurar de novo.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--configurar", action="store_true")
    if ap.parse_args().configurar:
        configurar()
    else:
        Bot().rodar()

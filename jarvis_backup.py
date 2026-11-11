"""
J.A.R.V.I.S. - assistente pessoal local (Ollama + interface web)

Uso:      python jarvis.py            (abre http://127.0.0.1:8765)
Opções:   --host 0.0.0.0 --port 8765 --no-browser

Assistente pessoal em Python. Tudo em um arquivo, dividido em módulos:

  1. Config         -> modelos, personalidade, limites (edite aqui primeiro)
  2. Ollama         -> cliente HTTP do Ollama (chat, load/unload, status)
  3. ThinkFilter    -> separa <think>...</think> do deepseek-r1
  4. ModelManager   -> carrega/descarrega modelos sob demanda
  5. WebSearch      -> pesquisa na web (DuckDuckGo, sem API key)
  6. Router         -> o modelo gerente decide quem responde
  7. Assistant      -> orquestra: roteia, busca, responde, guarda histórico
  8. UI (CSS/HTML/JS) -> interface estilo JARVIS
  9. Server         -> servidor HTTP + endpoints da API
"""
import argparse
import base64
import difflib
import glob
import html as htmllib
import importlib
import ipaddress
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ════════════════════════════════════════════════════════════════════════════
# 1. CONFIG
# ════════════════════════════════════════════════════════════════════════════
class Config:
    HOST = "127.0.0.1"
    PORT = 8765
    OLLAMA_URL = "http://127.0.0.1:11434"

    ASSISTANT_NAME = "J.A.R.V.I.S."
    USER_TITLE = "senhor"            # como ele te chama (ex.: "senhor", "chefe")
    LANGUAGE = "português do Brasil"

    # key -> usada internamente. keep_alive = quanto tempo fica na memória após o uso.
    MODELS = {
        "manager": {
            "name": "lfm3:1.7b", "label": "LFM", "role": "Gerência e conversa",
            "keep_alive": "30m", "options": {"temperature": 0.7, "num_ctx": 4096},
        },
        "knowledge": {
            "name": "gemma4:12b", "label": "GEMMA", "role": "Conhecimento e web",
            "keep_alive": "5m", "options": {"temperature": 0.4, "num_ctx": 8192},
        },
        "reasoning": {
            "name": "deepseek-r1:14b", "label": "DEEPSEEK", "role": "Raciocínio profundo",
            "keep_alive": "3m", "options": {"temperature": 0.6, "num_ctx": 8192},
        },
    }
    # Descarrega os modelos pesados que não serão usados antes de carregar outro.
    # O gerente (pequeno) permanece na memória para responder rápido.
    UNLOAD_OTHERS_ON_SWITCH = True
    # Tira gemma/deepseek da RAM assim que terminam de responder (o gerente continua carregado).
    UNLOAD_HEAVY_AFTER_RESPONSE = True

    # Mapeia "rota" decidida pelo gerente -> chave do modelo
    ROUTES = {"chat": "manager", "knowledge": "knowledge", "reasoning": "reasoning"}
    # Atalhos manuais: começar a mensagem com isso força o modelo
    FORCE_PREFIXES = {"/lfm": "chat", "/gemma": "knowledge", "/deepseek": "reasoning"}

    HISTORY_TURNS = 8          # pares usuário/assistente mantidos no contexto
    WEB_RESULTS = 5            # resultados da busca
    WEB_PAGES = 2              # páginas abertas para leitura
    WEB_CHARS = 2500           # caracteres de texto por página
    WEB_JSON_CHARS = 3000      # caracteres de dados estruturados (JSON/API) por página
    WEB_API_PROBES = 3         # APIs JSON descobertas dentro da página que serão testadas
    WEB_BROWSER = True         # usa Playwright (se instalado) para páginas renderizadas por JavaScript
    HTTP_TIMEOUT = 600         # segundos (carregar modelo grande pode demorar)
    # Ferramentas (YouTube, previsão do tempo)
    DEFAULT_LOCATION = "Curitiba, Paraná"   # usada quando o pedido não cita nenhuma cidade
    TOOL_ROUTES = {"youtube": "knowledge", "weather": "knowledge", "apps": "chat", "computer": "chat"}   # quem redige a resposta de cada ferramenta
    # Memória de longo prazo (arquivo markdown ao lado deste script)
    MEMORY_ENABLED = True
    MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_memory.md")
    MEMORY_PROMPT_CHARS = 3000      # quanto da memória entra no prompt (acima disso, só os fatos mais relevantes)
    MEMORY_MAX_CHARS = 30000        # tamanho máximo do arquivo
    # Controle de aplicativos (abrir/fechar). Só aceita pedidos vindos do próprio computador.
    APPS_ENABLED = True
    APP_ALIASES = {                 # apelido -> nomes a procurar, em ordem de preferência
        "navegador": ["google chrome", "chrome", "firefox", "microsoft edge", "brave", "safari"],
        "calculadora": ["calculadora", "calculator", "gnome calculator", "kcalc"],
        "bloco de notas": ["bloco de notas", "notepad", "textedit", "gedit", "kate"],
        "explorador de arquivos": ["explorador de arquivos", "file explorer", "finder", "files", "arquivos", "nautilus", "dolphin"],
        "gerenciador de arquivos": ["explorador de arquivos", "file explorer", "finder", "files", "arquivos", "nautilus", "dolphin"],
        "terminal": ["terminal", "windows terminal", "iterm", "gnome terminal", "konsole"],
        "vscode": ["visual studio code", "code"],
        "vs code": ["visual studio code", "code"],
        "musica": ["spotify", "musica", "music"],
        "configuracoes": ["configuracoes", "settings", "ajustes", "system settings"],
        "camera": ["camera", "cheese"],
    }
    # Programas fora dos menus: "nome": {"open": ["comando", "arg"], "process": "nome_do_processo"}
    CUSTOM_APPS = {
            "war thunder": {
                "open": [r"C:\Users\filip\WarThunder\launcher.exe"],
                "process": "aces.exe",
            },
    }
    # Controle do computador (pastas, sites, mensagens). Só aceita pedidos vindos do próprio computador.
    COMPUTER_ENABLED = True
    SEND_MODE = "auto"           # "confirm": pergunta antes de enviar | "draft": só digita, você aperta Enter | "auto": envia direto
    CONFIRM_TIMEOUT = 120           # segundos que o "posso enviar?" fica aguardando o seu "sim"
    VERIFY_RECIPIENT = False         # confere o título da janela antes de escrever (evita mandar para a pessoa errada)
    UI_DELAY = 1.0                  # multiplicador das esperas da automação; aumente se o PC for lento
    FOLDERS = {}                    # pastas suas: {"projetos": r"C:\Users\voce\Projetos"}
    CONTACTS = {
        "koga": {"search": "koga", "title": "♥.·:*¨¨*:·.♥ rick ♥.·:*¨¨*:·.♥"},
    }                   # só se o nome falado ≠ nome no app: {"abolinu": {"search": "abolinu", "title": "Nome exibido"}}
    ALLOW_EXECUTABLES = False       # False: nunca abre .exe, .bat, .ps1, .lnk e outros executáveis/scripts (por segurança)
    MESSENGERS = {                  # apps de mensagem suportados: como achar a janela e trocar de conversa
        "discord": {"name": "Discord", "process": "discord", "switch": "mod+k", "prefix": "@"},
        "slack": {"name": "Slack", "process": "slack", "switch": "mod+k", "prefix": ""},
    }
    SITES = {
        "youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com",
        "drive": "https://drive.google.com", "maps": "https://www.google.com/maps", "github": "https://github.com",
        "netflix": "https://www.netflix.com", "instagram": "https://www.instagram.com", "facebook": "https://www.facebook.com",
        "twitter": "https://x.com", "whatsapp web": "https://web.whatsapp.com", "wikipedia": "https://pt.wikipedia.org",
        "amazon": "https://www.amazon.com.br", "mercado livre": "https://www.mercadolivre.com.br",
        "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai", "spotify": "https://open.spotify.com",
    }
    SEARCH_SITES = {                # sites com busca: {q} é substituído pelo assunto
        "google": "https://www.google.com/search?q={q}", "youtube": "https://www.youtube.com/results?search_query={q}",
        "maps": "https://www.google.com/maps/search/{q}", "amazon": "https://www.amazon.com.br/s?k={q}",
        "wikipedia": "https://pt.wikipedia.org/w/index.php?search={q}", "mercado livre": "https://lista.mercadolivre.com.br/{q}",
    }
    # Pesquisa na web
    WEB_ALWAYS_FOR_KNOWLEDGE = True   # toda pergunta 'knowledge' pesquisa na web antes de responder
    ESCALATE_ON_UNCERTAINTY = True    # se o gerente disser que não sabe, refaz com gemma + web


# ── Prompts (personalidade e roteamento) ────────────────────────────────────
WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def memory_block(memory):
    if not memory:
        return ""
    return ("\n\nMEMÓRIA SOBRE O USUÁRIO (de conversas anteriores; use SOMENTE quando for relevante ao pedido, "
            "sem citá-la desnecessariamente e sem inventar além dela):\n" + memory)


def persona_prompt(extra="", memory=""):
    now = datetime.now()
    return (
        f"Você é {Config.ASSISTANT_NAME}, assistente pessoal inspirado no JARVIS de Tony Stark. "
        f"Trate o usuário por '{Config.USER_TITLE}'. Responda em {Config.LANGUAGE}, com elegância, "
        "eficiência e um humor seco e sutil. Seja conciso: suas respostas serão lidas em voz alta, "
        "então evite listas longas, tabelas, emojis e markdown pesado. "
        f"Agora é {WEEKDAYS[now.weekday()]}-feira, {now:%d/%m/%Y %H:%M}. {extra}"
        + memory_block(memory)
    ).strip()


ROUTER_PROMPT = """Você é o roteador de um assistente pessoal. Classifique o pedido do usuário.
Responda APENAS com JSON no formato:
{"route": "chat" | "knowledge" | "reasoning", "web": true | false, "query": "consulta de busca curta"}

- chat: conversa casual, cumprimentos, opinião simples, piadas, comandos triviais.
- knowledge: perguntas factuais, explicações, notícias, dados atuais, recomendações que exigem precisão.
- reasoning: matemática, lógica, programação, depuração, planejamento complexo, problemas difíceis.
- web: true se a resposta depende de informação atual ou verificável na internet (notícias, preços, clima, eventos, versões).
- query: se web for true, a melhor consulta de busca; senão, "".
"""

HEURISTIC_REASONING = re.compile(
    r"calcul|resolv|prove|demonstr|equa[cç][aã]o|integral|derivada|l[oó]gica|algoritmo|"
    r"c[oó]digo|programa|debug|bug|otimiz|passo a passo|quebra-cabe", re.I)
HEURISTIC_WEB = re.compile(
    r"hoje|ontem|esta semana|essa semana|not[ií]cia|cota[cç][aã]o|pre[cç]o|clima|temperatura|previs[aã]o|"
    r"[uú]ltim[oa]|atual|202\d|quem ganhou|resultado|placar|tabela|classifica[cç][aã]o|brasileir[aã]o|"
    r"campeonato|rodada|jogo d|d[oó]lar|euro|bitcoin|lan[cç]amento|vers[aã]o|eleic|elei[cç]", re.I)
HEURISTIC_QUESTION = re.compile(
    r"\?|^(qual|quais|quem|quando|onde|quanto|como (est[aá]|ficou|foi)|me (diga|fale|mostre|conte)|"
    r"pesquis|busque|procure|o que)", re.I)
# Frases que revelam que o modelo gerente não sabe responder (dispara pesquisa na web)
UNCERTAIN = re.compile(
    r"BUSCAR_WEB|tempo real|meus dados|treinamento|n[aã]o tenho acesso|n[aã]o consigo acessar|n[aã]o sei|"
    r"n[aã]o possuo|n[aã]o tenho informa|conex[aã]o digital|corte de conhecimento|"
    r"consulte (o|um|a|os|as)\b|recomendo (consultar|verificar)|site oficial", re.I)

MEM_EXPLICIT = re.compile(r"\b(lembre-se|lembre|anote|memorize|guarde|esque[çc]a|n[aã]o esque[çc]a)\b", re.I)
MEM_QUERY = re.compile(r"o que (?:voc[eê] )?(?:sabe|lembra|se lembra|conhece|guardou) (?:sobre|de|a respeito de) mim|"
                       r"do que eu gosto|qual (?:[eé] )?o meu nome|como eu me chamo|quem sou eu|"
                       r"minhas (?:prefer[eê]ncias|mem[oó]rias)|o que (?:voc[eê] )?guardou", re.I)
# Mensagens que PODEM conter algo a lembrar (filtro barato antes de acionar o curador)
MEM_CANDIDATE = re.compile(
    r"me chamo|meu nome|\bsou\b|gosto|adoro|\bamo\b|odeio|detesto|prefiro|\bmoro|trabalho|estudo|\btenho\b|\buso\b|"
    r"nasci|torço|curto|favorit|al[eé]rgic|casad|solteir|anivers[aá]rio|minha (?:esposa|namorada|filha|m[aã]e|irm[aã]|gata)|"
    r"meu (?:marido|namorado|filho|pai|irm[aã]o|cachorro|gato)|a partir de agora|sempre que|\bsonho\b|"
    r"lembre|anote|memorize|guarde|esque[çc]a", re.I)
CURATOR_PROMPT = """Você mantém a memória de longo prazo de um assistente pessoal. Leia APENAS a mensagem do usuário e decida o que vale lembrar em conversas futuras: gostos, interesses, hábitos, rotina, pessoas importantes (família, amigos, pets), trabalho/estudos, projetos, equipamentos que usa, datas importantes e preferências de como o assistente deve responder.
NÃO guarde: perguntas, pedidos pontuais, assuntos passageiros, senhas, documentos, números de cartão, nem fatos que já estão na memória.
Escreva cada fato como uma frase curta e autossuficiente, em terceira pessoa ("Gosta de...", "Chama-se...", "Tem um cachorro chamado...").
Só use "forget" se o usuário pedir explicitamente para esquecer algo; coloque ali um trecho curto do fato antigo.
Responda APENAS JSON: {"remember":[{"category":"pessoal|gostos|interesses|trabalho|projetos|preferencias|outros","fact":"..."}],"forget":["trecho"]}
Se não houver nada: {"remember":[],"forget":[]}
"Eu amo ficção científica e toco violão" -> {"remember":[{"category":"gostos","fact":"Gosta de ficção científica"},{"category":"interesses","fact":"Toca violão"}],"forget":[]}
"Qual a capital da França?" -> {"remember":[],"forget":[]}
"Esqueça que eu gosto de café" -> {"remember":[],"forget":["café"]}"""
AFFIRM = re.compile(r"^\W*(?:sim|s|pode(?: sim| enviar| mandar)?|confirmo|confirmado|confirma|isso(?: mesmo)?|claro|ok|certo|"
                    r"manda(?: ver)?|mande|envia|envie|vai|positivo|afirmativo)\b", re.I)
DENY = re.compile(r"^\W*(?:n[aã]o|nao|cancel\w*|deixa|esquece|pare|para|negativo)\b", re.I)
PC_PROMPT = """Extraia do pedido os dados para controlar o computador. Responda APENAS JSON, só com os campos que se aplicam:
{"folder": "nome da pasta ou caminho", "file": "nome (ou parte do nome) do arquivo", "site": "nome do site, domínio ou URL", "query": "assunto a pesquisar ou vídeo a tocar", "channel": "canal do YouTube, se citado", "latest": true | false, "play": true | false, "app": "discord | slack", "contact": "nome do destinatário", "message": "texto EXATO da mensagem a enviar"}
play = true quando o usuário quer abrir/tocar um vídeo específico. latest = true se for o vídeo mais recente de um canal.
"abra o explorador de arquivos na pasta de imagens" -> {"folder":"imagens"}
"abre a pasta downloads" -> {"folder":"downloads"}
"abra o youtube" -> {"site":"youtube"}
"toque no youtube a música Bohemian Rhapsody" -> {"site":"youtube","query":"Bohemian Rhapsody","play":true}
"abre o último vídeo do canal Manual do Mundo" -> {"site":"youtube","channel":"Manual do Mundo","latest":true,"play":true}
"abra o site da Amazon" -> {"site":"amazon"}
"pesquise receita de bolo no google" -> {"site":"google","query":"receita de bolo"}
"abre o discord e manda uma mensagem pro Pedro dizendo que chego em 10 minutos" -> {"app":"discord","contact":"Pedro","message":"chego em 10 minutos"}
"mande um oi para o ninguem7343 no discord por favor" -> {"app":"discord","contact":"ninguém7343","message":"oi"}
"manda um salve para o Fulano no discord" -> {"app":"discord","contact":"Fulano","message":"salve"}
"abra o arquivo relatorio.pdf na pasta documentos" -> {"file":"relatorio.pdf","folder":"documentos"}
"abre o último arquivo baixado" -> {"folder":"downloads","latest":true}
"abra a foto praia dentro de imagens" -> {"file":"praia","folder":"imagens"}"""
CHAT_HINT = ("Se o pedido exigir fatos, dados atuais (esportes, notícias, preços, clima) ou você não tiver "
             "certeza da resposta, responda APENAS com a palavra BUSCAR_WEB, sem mais nada. "
             "Nunca diga que não tem acesso à internet.")
WEB_INSTRUCTION = ("Você TEM acesso à internet: os resultados de busca abaixo foram obtidos agora. "
                   "Responda com base neles, de forma direta, citando o nome do site quando relevante. "
                   "Nunca diga que não tem acesso a dados em tempo real. Se os resultados forem "
                   "insuficientes, diga o que encontrou e o que faltou.\n\nRESULTADOS DA BUSCA:\n")
TOOL_INSTRUCTION = ("Os dados abaixo foram obtidos AGORA por uma ferramenta confiável. Use-os exatamente como "
                    "estão, sem inventar nem alterar números, datas ou títulos. Se o usuário pedir algo que não "
                    "está nos dados, diga isso. Nunca diga que não tem acesso a dados em tempo real.\n\nDADOS:\n")
YT_PROMPT = """Extraia do pedido os dados para buscar no YouTube. Responda APENAS JSON:
{"channel": "nome ou @handle do canal, ou vazio", "query": "assunto/título a procurar, ou vazio", "latest": true | false}
latest = true se o usuário quer o vídeo mais recente / último / novo.
"qual o último vídeo do canal Manual do Mundo?" -> {"channel":"Manual do Mundo","query":"","latest":true}
"acha o vídeo do Nerdologia sobre buracos negros" -> {"channel":"Nerdologia","query":"buracos negros","latest":false}
"vídeos de receita de pão de queijo" -> {"channel":"","query":"receita de pão de queijo","latest":false}"""
WX_PROMPT = """Extraia a cidade do pedido. Responda APENAS JSON: {"location": "cidade, estado ou país; vazio se o usuário não citou nenhum lugar"}
"vai chover em São Paulo amanhã?" -> {"location":"São Paulo"}
"como está o tempo hoje?" -> {"location":""}"""
WEB_FAILED_NOTE = ("A busca na web falhou agora. Diga ao usuário, em uma frase, que não conseguiu consultar a "
                   "internet neste momento. NÃO invente dados atuais.")
HEURISTIC_KNOWLEDGE = re.compile(r"^(o que|quem|quando|onde|por que|porque|como funciona|explique|qual)", re.I)


# ════════════════════════════════════════════════════════════════════════════
# 2. OLLAMA
# ════════════════════════════════════════════════════════════════════════════
def norm(name):
    """'gemma4:12b' e 'gemma4:12b' iguais; sem tag vira ':latest'."""
    return name if ":" in name else name + ":latest"


class Ollama:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def _open(self, path, payload=None, timeout=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, headers={"Content-Type": "application/json"},
            method="POST" if data is not None else "GET")
        return urllib.request.urlopen(req, timeout=timeout or Config.HTTP_TIMEOUT)

    def alive(self):
        try:
            self._open("/api/tags", timeout=3).close()
            return True
        except Exception:
            return False

    def installed(self):
        with self._open("/api/tags", timeout=5) as r:
            return {norm(m["name"]) for m in json.load(r).get("models", [])}

    def loaded(self):
        with self._open("/api/ps", timeout=5) as r:
            return {norm(m["name"]) for m in json.load(r).get("models", [])}

    def unload(self, model):
        try:
            self._open("/api/generate", {"model": model, "keep_alive": 0}, timeout=30).close()
        except Exception:
            pass

    def stream(self, model, messages, options=None, keep_alive="5m", fmt=None):
        """Gera tuplas (tipo, texto): tipo = 'think' | 'text'."""
        payload = {"model": model, "messages": messages, "stream": True,
                   "keep_alive": keep_alive, "options": options or {}}
        if fmt:
            payload["format"] = fmt
        with self._open("/api/chat", payload) as r:
            for line in r:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise RuntimeError(chunk["error"])
                msg = chunk.get("message", {})
                if msg.get("thinking"):
                    yield "think", msg["thinking"]
                if msg.get("content"):
                    yield "text", msg["content"]

    def chat(self, model, messages, **kw):
        return "".join(t for k, t in self.stream(model, messages, **kw) if k == "text")


# ════════════════════════════════════════════════════════════════════════════
# 3. THINK FILTER  (deepseek-r1 pode emitir <think>...</think> no texto)
# ════════════════════════════════════════════════════════════════════════════
class ThinkFilter:
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.buf, self.inside = "", False

    def feed(self, text):
        self.buf += text
        out = []
        while True:
            tag = self.CLOSE if self.inside else self.OPEN
            kind = "think" if self.inside else "text"
            i = self.buf.find(tag)
            if i >= 0:
                if i:
                    out.append((kind, self.buf[:i]))
                self.buf = self.buf[i + len(tag):]
                self.inside = not self.inside
                continue
            keep = 0  # segura um possível início de tag cortado entre chunks
            for n in range(min(len(tag) - 1, len(self.buf)), 0, -1):
                if tag.startswith(self.buf[-n:]):
                    keep = n
                    break
            emit = self.buf[:len(self.buf) - keep]
            if emit:
                out.append((kind, emit))
            self.buf = self.buf[len(self.buf) - keep:]
            return out

    def flush(self):
        rest, self.buf = self.buf, ""
        return [("think" if self.inside else "text", rest)] if rest else []


# ════════════════════════════════════════════════════════════════════════════
# 4. MODEL MANAGER  (carrega sob demanda, descarrega os outros)
# ════════════════════════════════════════════════════════════════════════════
class ModelManager:
    def __init__(self, ollama):
        self.ollama = ollama

    def cfg(self, key):
        return Config.MODELS[key]

    def prepare(self, key, emit):
        """Garante o cenário de memória antes de usar o modelo `key`."""
        loaded = self.ollama.loaded()
        if Config.UNLOAD_OTHERS_ON_SWITCH and key != "manager":
            for k, m in Config.MODELS.items():
                if k not in ("manager", key) and norm(m["name"]) in loaded:
                    emit("status", f"Liberando memória: {m['label']}")
                    self.ollama.unload(m["name"])
        if norm(self.cfg(key)["name"]) not in loaded:
            emit("status", f"Carregando {self.cfg(key)['label']}...")

    def unload_all(self):
        for m in Config.MODELS.values():
            self.ollama.unload(m["name"])

    def status(self):
        try:
            inst, load = self.ollama.installed(), self.ollama.loaded()
            online = True
        except Exception:
            inst, load, online = set(), set(), False
        models = [{"key": k, "name": m["name"], "label": m["label"], "role": m["role"],
                   "installed": norm(m["name"]) in inst, "loaded": norm(m["name"]) in load}
                  for k, m in Config.MODELS.items()]
        return {"ollama": online, "models": models}


# ════════════════════════════════════════════════════════════════════════════
# 5. WEB SEARCH
# ════════════════════════════════════════════════════════════════════════════
class _PageParser(HTMLParser):
    """Texto legível (tabelas viram linhas 'a | b | c') + conteúdo bruto dos <script>."""
    SKIP = {"style", "nav", "footer", "aside", "noscript", "svg", "form", "head"}

    def __init__(self):
        super().__init__()
        self.lines, self.scripts = [], []
        self.skip, self.script, self.stype = 0, None, ""
        self.row, self.cell = None, None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.script, self.stype = [], (dict(attrs).get("type") or "").lower()
        elif tag in self.SKIP:
            self.skip += 1
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag == "script":
            if self.script is not None:
                self.scripts.append((self.stype, "".join(self.script)))
            self.script = None
        elif tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(self.cell))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.lines.append(" | ".join(self.row))
            self.row = None

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
            return
        t = " ".join(data.split())
        if self.skip or not t:
            return
        if self.cell is not None:
            self.cell.append(t)
        elif len(t) >= 25:
            self.lines.append(t)


# ── Dados estruturados (JSON embutido em scripts ou vindo de APIs) ──────────
def _flat(d, prefix="", depth=2):
    out = {}
    for k, v in d.items():
        key = prefix + str(k)
        if isinstance(v, (str, int, float)) and not isinstance(v, bool):
            if len(str(v)) < 80:
                out[key] = v
        elif isinstance(v, dict) and depth:
            out.update(_flat(v, key + ".", depth - 1))
        elif isinstance(v, list) and v and all(
                isinstance(i, dict) and "name" in i and ("value" in i or "displayValue" in i) for i in v):
            for i in v:                      # [{name:'points', value:30}, ...] -> points=30
                out[i["name"]] = i.get("displayValue", i.get("value"))
    return out


def json_to_text(obj, budget):
    """Procura listas de objetos (= tabelas) dentro de um JSON e as converte em linhas de texto."""
    lines, size = [], [0]

    def walk(x, name):
        if size[0] > budget:
            return
        if isinstance(x, list) and len(x) >= 3 and all(isinstance(i, dict) for i in x):
            rows = [r for r in (_flat(i) for i in x[:40]) if len(r) >= 3]
            if rows:
                lines.append(f"[{name}]")
                for r in rows:
                    ln = " | ".join(f"{k}={v}" for k, v in r.items())
                    lines.append(ln)
                    size[0] += len(ln)
                return
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, k)
        elif isinstance(x, list):
            for v in x[:40]:
                walk(v, name)

    walk(obj, "dados")
    return "\n".join(lines)[:budget]


def json_blobs(scripts):
    """JSON em <script type=json>, __NEXT_DATA__, window.__ESTADO__ = {...}, JSON.parse(...)."""
    dec, out = json.JSONDecoder(), []
    for stype, body in scripts:
        body = body.strip()
        if not body:
            continue
        if "json" in stype:
            try:
                out.append(json.loads(body))
            except ValueError:
                pass
        elif len(body) > 200:
            for n, m in enumerate(re.finditer(r"(?:=|JSON\.parse\()\s*(?=[{\[])", body)):
                if n >= 5:
                    break
                try:
                    out.append(dec.raw_decode(body[m.end():])[0])
                except ValueError:
                    pass
    return out[:12]


class PageReader:
    """Lê páginas: texto + tabelas + JSON embutido + APIs descobertas + (opcional) navegador real."""
    API_HINT = re.compile(r"api|json|graphql|/v\d/|ranking|standing|classifica|tabela|rodada|data\.", re.I)
    API_BAD = re.compile(r"google|doubleclick|facebook|twitter|analytics|gtm|adservice|hotjar|sentry|"
                         r"cloudflare|fonts\.|\.(js|css|png|jpe?g|gif|svg|woff2?|ico)(\?|$)", re.I)

    def __init__(self, ua):
        self.ua = ua

    @staticmethod
    def public(url):
        """Bloqueia localhost/rede privada (evita que uma página mande o assistente acessar sua rede)."""
        try:
            u = urllib.parse.urlparse(url)
            if u.scheme not in ("http", "https") or not u.hostname:
                return False
            return all(ipaddress.ip_address(i[4][0]).is_global for i in socket.getaddrinfo(u.hostname, None))
        except Exception:
            return False

    def get(self, url, accept="text/html,application/xhtml+xml,*/*", limit=600_000, headers=None):
        if not self.public(url):
            raise ValueError("URL bloqueada")
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": accept,
                                                   "Accept-Language": "pt-BR,pt;q=0.9", **(headers or {})})
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.read(limit).decode("utf-8", "ignore")

    def get_json(self, url):
        return json.loads(self.get(url, "application/json"))

    def probe_apis(self, raw):
        """Procura URLs de API dentro do HTML/scripts da página e tenta lê-las como JSON."""
        urls, seen = [], set()
        for u in re.findall(r"https?://[^\s\"'<>\\)]+", raw.replace("\\/", "/")):
            u = htmllib.unescape(u).rstrip(",;")
            if u not in seen and self.API_HINT.search(u) and not self.API_BAD.search(u):
                seen.add(u)
                urls.append(u)
        out = []
        for u in urls[:Config.WEB_API_PROBES * 3]:
            try:
                t = json_to_text(self.get_json(u), Config.WEB_JSON_CHARS)
                if t:
                    out.append(f"[API {u[:90]}]\n{t}")
            except Exception:
                continue
            if len(out) >= Config.WEB_API_PROBES:
                break
        return "\n".join(out)

    def extract(self, raw, probe=True):
        parser = _PageParser()
        try:
            parser.feed(raw)
        except Exception:
            pass
        body = "\n".join(parser.lines)[:Config.WEB_CHARS]
        data = "\n".join(t for t in (json_to_text(j, Config.WEB_JSON_CHARS) for j in json_blobs(parser.scripts)) if t)
        data = data[:Config.WEB_JSON_CHARS]
        if probe and len(body) + len(data) < 600:        # página "vazia": os dados vêm de uma API
            data += "\n" + self.probe_apis(raw)
        return body + (("\n[dados embutidos na página]\n" + data.strip()) if data.strip() else "")

    def text(self, url):
        try:
            return self.extract(self.get(url))
        except Exception:
            return ""

    def render(self, url):
        """Navegador real (Playwright) para páginas 100% JavaScript. Opcional: pip install playwright."""
        if not Config.WEB_BROWSER or not self.public(url):
            return ""
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except ImportError:
            return ""
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    page = browser.new_page(user_agent=self.ua)
                    page.goto(url, wait_until="networkidle", timeout=20000)
                    html = page.content()
                finally:
                    browser.close()
            return self.extract(html, probe=False)
        except Exception:
            return ""


# ── Fontes estruturadas (APIs públicas, sem JavaScript) ─────────────────────
class Providers:
    """Para certos assuntos existe uma API pronta, mais confiável que raspar página."""
    LEAGUES = [  # (regex, código ESPN, nome). A ordem importa: mais específico primeiro.
        (r"s[eé]rie b|brasileir[aã]o b", "bra.2", "Brasileirão Série B"),
        (r"copa do brasil", "bra.copa_do_brazil", "Copa do Brasil"),
        (r"brasileir[aã]o|s[eé]rie a\b|campeonato brasileiro", "bra.1", "Brasileirão Série A"),
        (r"libertadores", "conmebol.libertadores", "Libertadores"),
        (r"sul-?americana", "conmebol.sudamericana", "Sul-Americana"),
        (r"champions", "uefa.champions", "Champions League"),
        (r"europa league", "uefa.europa", "Europa League"),
        (r"premier league", "eng.1", "Premier League"),
        (r"la ?liga|campeonato espanhol", "esp.1", "La Liga"),
        (r"bundesliga", "ger.1", "Bundesliga"),
        (r"serie a italiana|calcio|campeonato italiano", "ita.1", "Serie A (Itália)"),
        (r"ligue 1", "fra.1", "Ligue 1"),
        (r"campeonato argentino|liga argentina", "arg.1", "Liga Argentina"),
        (r"mls\b", "usa.1", "MLS"),
    ]
    STAND = re.compile(r"tabela|classifica|posi[cç]|l[ií]der|rebaix|pontos|colocad|g-?4|z-?4", re.I)
    GAMES = re.compile(r"jogo|placar|resultado|rodada|partida|ganhou|perdeu|empat|quanto ficou|hoje|ontem|amanh", re.I)
    BASE = "https://site.api.espn.com/apis"

    @staticmethod
    def _standings(data):
        rows = []
        for grp in (data.get("children") or [data]):
            entries = (grp.get("standings") or {}).get("entries") or []
            for e in entries:
                st = {x.get("name"): x.get("displayValue", x.get("value")) for x in e.get("stats", [])}
                try:
                    rank = int(float(st.get("rank", 999)))
                except (TypeError, ValueError):
                    rank = 999
                rows.append((rank, f"{st.get('rank', '?')}º {e.get('team', {}).get('displayName', '?')} | "
                                   f"pts {st.get('points', '?')} | J {st.get('gamesPlayed', '?')} | "
                                   f"V {st.get('wins', '?')} E {st.get('ties', '?')} D {st.get('losses', '?')} | "
                                   f"SG {st.get('pointDifferential', '?')}"))
        rows.sort(key=lambda r: r[0])
        return "\n".join(r[1] for r in rows) or json_to_text(data, Config.WEB_JSON_CHARS)

    @staticmethod
    def _scoreboard(data):
        lines = []
        for ev in data.get("events", [])[:20]:
            comp = (ev.get("competitions") or [{}])[0]
            cs = sorted(comp.get("competitors", []), key=lambda c: c.get("homeAway") != "home")
            teams = " x ".join(f"{c.get('team', {}).get('displayName', '?')} {c.get('score', '')}".strip() for c in cs)
            status = (ev.get("status") or {}).get("type", {}).get("description", "")
            lines.append(f"{str(ev.get('date', ''))[:16]} | {teams} | {status}")
        return "\n".join(lines)

    @classmethod
    def lookup(cls, query, get_json):
        """Devolve (texto, [urls]) ou None."""
        q = query.lower()
        hit = next(((c, n) for rx, c, n in cls.LEAGUES if re.search(rx, q)), None)
        if not hit:
            return None
        code, name = hit
        wants_s, wants_g = bool(cls.STAND.search(q)), bool(cls.GAMES.search(q))
        both = not (wants_s or wants_g)
        parts, urls = [], []
        jobs = []
        if wants_s or both:
            jobs.append(("CLASSIFICAÇÃO", f"{cls.BASE}/v2/sports/soccer/{code}/standings", cls._standings))
        if wants_g or both:
            jobs.append(("JOGOS (recentes/próximos)", f"{cls.BASE}/site/v2/sports/soccer/{code}/scoreboard",
                         cls._scoreboard))
        for title, url, fmt in jobs:
            try:
                txt = fmt(get_json(url))
                if txt.strip():
                    parts.append(f"FONTE ESTRUTURADA (ESPN, dados atuais) - {name} - {title}:\n{txt}")
                    urls.append(url)
            except Exception:
                continue
        return ("\n\n".join(parts)[:3500], urls) if parts else None


# ── Previsão do tempo (Open-Meteo: gratuita, sem chave) ─────────────────────
class Weather:
    GEO = "https://geocoding-api.open-meteo.com/v1/search?"
    API = "https://api.open-meteo.com/v1/forecast?"
    WMO = {0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado",
           45: "neblina", 48: "neblina com geada", 51: "garoa fraca", 53: "garoa moderada", 55: "garoa intensa",
           56: "garoa congelante", 57: "garoa congelante intensa", 61: "chuva fraca", 63: "chuva moderada",
           65: "chuva forte", 66: "chuva congelante", 67: "chuva congelante forte", 71: "neve fraca",
           73: "neve moderada", 75: "neve forte", 77: "grãos de neve", 80: "pancadas de chuva fracas",
           81: "pancadas de chuva moderadas", 82: "pancadas de chuva violentas", 85: "pancadas de neve fracas",
           86: "pancadas de neve fortes", 95: "trovoada", 96: "trovoada com granizo", 99: "trovoada com granizo forte"}

    def __init__(self, reader):
        self.rd = reader

    def geocode(self, place):
        name, _, hint = place.partition(",")
        hint = hint.strip().lower()
        res = self.rd.get_json(self.GEO + urllib.parse.urlencode(
            {"name": name.strip(), "count": 10, "language": "pt", "format": "json"})).get("results") or []
        if not res:
            raise ValueError(f"local não encontrado: {place}")
        if hint:
            for r in res:
                if hint in " ".join(str(r.get(k, "")) for k in ("admin1", "admin2", "country", "country_code")).lower():
                    return r
        return res[0]

    @classmethod
    def desc(cls, code):
        return cls.WMO.get(code, f"código {code}")

    def report(self, place):
        g = self.geocode(place)
        url = self.API + urllib.parse.urlencode({
            "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto", "forecast_days": 7,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,"
                       "wind_speed_10m,wind_gusts_10m,is_day",
            "hourly": "temperature_2m,precipitation_probability,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                     "precipitation_probability_max,wind_speed_10m_max,uv_index_max,sunrise,sunset"})
        d = self.rd.get_json(url)
        v = lambda x, u="": "?" if x is None else f"{x}{u}"
        c, h, dd = d["current"], d["hourly"], d["daily"]
        now = datetime.fromisoformat(c["time"])
        local = ", ".join(x for x in (g.get("name"), g.get("admin1"), g.get("country")) if x)
        lines = [f"PREVISÃO DO TEMPO - {local} (horário local {now:%d/%m/%Y %H:%M}; fonte: Open-Meteo)",
                 f"AGORA: {self.desc(c['weather_code'])}, {v(c['temperature_2m'], '°C')} "
                 f"(sensação {v(c['apparent_temperature'], '°C')}), umidade {v(c['relative_humidity_2m'], '%')}, "
                 f"vento {v(c['wind_speed_10m'], ' km/h')} (rajadas {v(c['wind_gusts_10m'], ' km/h')}), "
                 f"chuva neste momento {v(c['precipitation'], ' mm')}"]
        times = [datetime.fromisoformat(t) for t in h["time"]]
        idx = [i for i, t in enumerate(times) if t >= now.replace(minute=0)][:16:3]
        lines.append("PRÓXIMAS HORAS: " + "; ".join(
            f"{times[i]:%Hh} {self.desc(h['weather_code'][i])}, {v(h['temperature_2m'][i], '°C')}, "
            f"chance de chuva {v(h['precipitation_probability'][i], '%')}" for i in idx))
        lines.append("PREVISÃO DIÁRIA:")
        for i, day in enumerate(dd["time"]):
            dt = datetime.fromisoformat(day)
            label = "hoje" if i == 0 else "amanhã" if i == 1 else WEEKDAYS[dt.weekday()]
            extra = f", nascer do sol {dd['sunrise'][i][11:16]}, pôr do sol {dd['sunset'][i][11:16]}" if i == 0 else ""
            wd = f", {WEEKDAYS[dt.weekday()]}" if i < 2 else ""
            lines.append(f"- {label} ({dt:%d/%m}{wd}): {self.desc(dd['weather_code'][i])}, "
                         f"mín {v(dd['temperature_2m_min'][i], '°C')} / máx {v(dd['temperature_2m_max'][i], '°C')}, "
                         f"chuva {v(dd['precipitation_sum'][i], ' mm')} (chance {v(dd['precipitation_probability_max'][i], '%')}), "
                         f"vento até {v(dd['wind_speed_10m_max'][i], ' km/h')}, UV {v(dd['uv_index_max'][i])}{extra}")
        return "\n".join(lines), [url]


# ── YouTube (feed RSS oficial dos canais + página de busca; sem API key) ────
class YouTube:
    HEAD = {"Cookie": "SOCS=CAI; CONSENT=YES+1"}
    FILTER = {"video": "EgIQAQ%3D%3D", "channel": "EgIQAg%3D%3D", "recent": "CAISAhAB"}
    NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
          "m": "http://search.yahoo.com/mrss/"}

    def __init__(self, reader):
        self.rd = reader

    @staticmethod
    def _t(x):
        return "" if not x else x.get("simpleText") or "".join(r.get("text", "") for r in x.get("runs", []))

    @staticmethod
    def _find(obj, key, out):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == key and isinstance(v, dict):
                    out.append(v)
                else:
                    YouTube._find(v, key, out)
        elif isinstance(obj, list):
            for v in obj:
                YouTube._find(v, key, out)
        return out

    def _search_data(self, query, flt):
        url = "https://www.youtube.com/results?" + urllib.parse.urlencode(
            {"search_query": query, "hl": "pt", "gl": "BR"}) + "&sp=" + self.FILTER[flt]
        raw = self.rd.get(url, limit=3_000_000, headers=self.HEAD)
        m = re.search(r"ytInitialData\s*=\s*", raw)
        if not m:
            raise ValueError("YouTube não devolveu dados de busca")
        return json.JSONDecoder().raw_decode(raw[m.end():])[0]

    def search_videos(self, query, recent=False):
        out = []
        for v in self._find(self._search_data(query, "recent" if recent else "video"), "videoRenderer", []):
            run = (v.get("ownerText", {}).get("runs") or [{}])[0]
            out.append({"id": v.get("videoId"), "title": self._t(v.get("title")), "channel": self._t(v.get("ownerText")),
                        "channel_id": run.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId"),
                        "when": self._t(v.get("publishedTimeText")), "len": self._t(v.get("lengthText")),
                        "views": self._t(v.get("viewCountText"))})
        return [v for v in out if v["id"]][:8]

    def find_channel(self, name):
        """Devolve (channel_id, nome, alternativas)."""
        if name.startswith("@"):
            raw = self.rd.get("https://www.youtube.com/" + urllib.parse.quote(name), limit=1_500_000, headers=self.HEAD)
            m = re.search(r"channel_id=(UC[\w-]{22})", raw) or re.search(r'"channelId":"(UC[\w-]{22})"', raw)
            t = re.search(r'<meta property="og:title" content="([^"]+)"', raw)
            if m:
                return m.group(1), htmllib.unescape(t.group(1)) if t else name, []
        chans = [(c.get("channelId"), self._t(c.get("title")))
                 for c in self._find(self._search_data(name, "channel"), "channelRenderer", [])]
        chans = [c for c in chans if c[0]]
        if chans:
            return chans[0][0], chans[0][1], [c[1] for c in chans[1:4]]
        for v in self.search_videos(name):                        # plano B: dono do primeiro vídeo achado
            if v["channel_id"]:
                return v["channel_id"], v["channel"], []
        return None, name, []

    def feed(self, cid, n=6):
        root = ET.fromstring(self.rd.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
                                         "application/atom+xml,*/*", headers=self.HEAD))
        out = []
        for e in root.findall("a:entry", self.NS)[:n]:
            st = e.find("m:group/m:community/m:statistics", self.NS)
            out.append({"id": e.findtext("yt:videoId", namespaces=self.NS), "title": e.findtext("a:title", namespaces=self.NS),
                        "published": e.findtext("a:published", namespaces=self.NS),
                        "views": st.get("views") if st is not None else None})
        return out

    @staticmethod
    def _ago(iso):
        dt = datetime.fromisoformat(iso)
        secs = (datetime.now(timezone.utc) - dt).total_seconds()
        ago = (f"há {int(secs // 86400)} dia(s)" if secs >= 86400 else f"há {int(secs // 3600)} hora(s)")
        return f"{dt.astimezone():%d/%m/%Y %H:%M} ({ago})"

    @staticmethod
    def _line(v):
        bits = [v["title"], f"canal: {v['channel']}" if v.get("channel") else "", f"publicado {v['when']}" if v.get("when") else "",
                f"duração {v['len']}" if v.get("len") else "", v.get("views") or "", f"https://www.youtube.com/watch?v={v['id']}"]
        return "- " + " | ".join(b for b in bits if b)

    def run(self, channel, query, latest):
        parts, urls = [], []
        if channel:
            cid, cname, alts = self.find_channel(channel)
            if cid:
                feed = self.feed(cid)
                lines = [f"CANAL: {cname} (https://www.youtube.com/channel/{cid})" +
                         (f" | outros canais parecidos: {', '.join(alts)}" if alts else ""),
                         "ÚLTIMOS VÍDEOS PUBLICADOS (do mais recente ao mais antigo; o feed inclui Shorts e lives):"]
                for e in feed:
                    views = f" | {int(e['views']):,} visualizações".replace(",", ".") if e["views"] else ""
                    lines.append(f"- {e['title']} | publicado {self._ago(e['published'])}{views} | "
                                 f"https://www.youtube.com/watch?v={e['id']}")
                    urls.append(f"https://www.youtube.com/watch?v={e['id']}")
                parts.append("\n".join(lines))
                if query:                                          # assunto específico dentro do canal
                    vids = self.search_videos(f"{cname} {query}")
                    mine = [v for v in vids if v["channel_id"] == cid] or vids
                    parts.append(f"BUSCA '{query}' NO CANAL:\n" + "\n".join(self._line(v) for v in mine[:5]))
                    urls += [f"https://www.youtube.com/watch?v={v['id']}" for v in mine[:5]]
                return "\n\n".join(parts), urls
            query = f"{channel} {query}".strip()
        vids = self.search_videos(query, recent=latest)
        if not vids:
            raise ValueError("nenhum vídeo encontrado")
        head = "VÍDEOS ENCONTRADOS (mais recentes primeiro)" if latest else "VÍDEOS ENCONTRADOS (relevância)"
        return head + f" para '{query}':\n" + "\n".join(self._line(v) for v in vids[:6]), \
            [f"https://www.youtube.com/watch?v={v['id']}" for v in vids[:6]]


# ── Memória de longo prazo (markdown) ───────────────────────────────────────
def fold(s):
    """minúsculas, sem acentos e sem pontuação: para comparar textos."""
    s = unicodedata.normalize("NFKD", str(s).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


class Memory:
    CATS = {"pessoal": "Pessoal", "gostos": "Gostos", "interesses": "Interesses", "trabalho": "Trabalho e estudos",
            "projetos": "Projetos", "preferencias": "Preferências sobre o assistente", "outros": "Outros"}
    HEADER = ("# Memória do J.A.R.V.I.S.\n\n> Fatos sobre o usuário guardados entre conversas. O assistente atualiza este "
              "arquivo sozinho; você também pode editar à mão (um item por linha, no formato `- fato`).\n")
    SENSITIVE = re.compile(r"senha|password|token|api[ -]?key|cart[aã]o de cr[eé]dito|\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\d{12,}", re.I)
    DATE = re.compile(r"\s*_\(\d{4}-\d{2}-\d{2}\)_\s*$")

    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()

    def read(self):
        with self.lock:
            try:
                with open(self.path, encoding="utf-8") as f:
                    return f.read()
            except FileNotFoundError:
                return self.HEADER

    def write(self, text):
        with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text.rstrip() + "\n")
            os.replace(tmp, self.path)        # gravação atômica: nunca deixa o arquivo pela metade

    def facts(self):
        """Lista de (seção, fato)."""
        out, sec = [], ""
        for ln in self.read().splitlines():
            if ln.startswith("## "):
                sec = ln[3:].strip()
            elif ln.startswith("- "):
                out.append((sec, self.DATE.sub("", ln[2:]).strip()))
        return out

    def add(self, category, fact):
        fact = " ".join(str(fact).split())[:240]
        if len(fact) < 6 or self.SENSITIVE.search(fact):
            return False
        head = "## " + self.CATS.get(category, "Outros")
        with self.lock:
            text = self.read()
            key = fold(fact)
            for _, old in self.facts():
                k = fold(old)
                if key == k or (len(k) > 12 and (key in k or k in key)):
                    return False                                   # já existe
            if len(text) > Config.MEMORY_MAX_CHARS:
                return False
            lines = text.rstrip().splitlines()
            bullet = f"- {fact} _({datetime.now():%Y-%m-%d})_"
            if head in lines:
                i = lines.index(head) + 1
                while i < len(lines) and not lines[i].startswith("## "):
                    i += 1
                while lines[i - 1].strip() == "":
                    i -= 1
                lines.insert(i, bullet)
            else:
                lines += ["", head, bullet]
            self.write("\n".join(lines))
            return True

    def forget(self, needle):
        n = fold(needle)
        if len(n) < 4:
            return []
        with self.lock:
            kept, gone = [], []
            for ln in self.read().splitlines():
                if ln.startswith("- ") and n in fold(self.DATE.sub("", ln[2:])) and len(gone) < 5:
                    gone.append(self.DATE.sub("", ln[2:]).strip())
                else:
                    kept.append(ln)
            if gone:
                self.write("\n".join(kept))
            return gone

    def prompt_block(self, query="", everything=False):
        """Fatos para o prompt: todos se couberem; senão os mais relevantes ao pedido."""
        lines = [f"- [{sec}] {f}" if sec else f"- {f}" for sec, f in self.facts()]
        if everything or sum(map(len, lines)) <= Config.MEMORY_PROMPT_CHARS:
            return "\n".join(lines)
        words = {w for w in fold(query).split() if len(w) > 3}
        order = sorted(range(len(lines)), key=lambda i: (-len(words & set(fold(lines[i]).split())), -i))
        chosen, size = [], 0
        for i in order:
            if size + len(lines[i]) <= Config.MEMORY_PROMPT_CHARS:
                chosen.append(i)
                size += len(lines[i])
        return "\n".join(lines[i] for i in sorted(chosen))


# ── Aplicativos instalados: abrir e fechar ──────────────────────────────────
PROTECTED = {"python", "python3", "pythonw", "py", "explorer", "dwm", "winlogon", "csrss", "lsass", "services",
             "svchost", "system", "windowsterminal", "cmd", "conhost", "powershell", "pwsh", "finder",
             "systemuiserver", "dock", "loginwindow", "terminal", "iterm2", "gnome terminal", "gnome shell",
             "konsole", "xterm", "plasmashell", "kwin"}


def protected(name):
    """Programas que nunca são fechados: sistema, terminais (o assistente roda num) e o próprio Ollama."""
    f = fold(name)
    return f in PROTECTED or f.startswith("ollama") or f.startswith("python")


class Apps:
    OPEN_V = ("abra", "abre", "abrir", "inicie", "iniciar", "execute", "executar", "lance", "lancar", "lançar",
              "rode", "rodar", "ligue", "ligar")
    CLOSE_V = ("feche", "fecha", "fechar", "encerre", "encerra", "encerrar", "finalize", "finalizar", "termine",
               "terminar", "mate", "matar")
    RX = re.compile(r"\b(?P<v>" + "|".join(OPEN_V + CLOSE_V) + r")\b\s+(?:(?:o|a|os|as|um|uma)\s+)?"
                    r"(?:(?:aplicativo|app|programa)\s+(?:d[oae]s?\s+)?)?(?P<t>[^,.;!?\n]+)", re.I)
    NOISE = re.compile(r"\b(?:pra|para) mim\b|\bpor favor\b|\bagora\b|\bno (?:meu )?(?:computador|pc|notebook)\b|"
                       r"\b(?:[àa]) for[çc]a\b|\bfor[çc](?:e|ar|ad[oa])\b", re.I)
    FORCE = re.compile(r"\bfor[çc](?:e|ar|ad[oa])\b|à for[çc]a|\bmate\b|\bmatar\b", re.I)
    NOWIN = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

    def __init__(self):
        self.lock = threading.RLock()
        self._cache, self._t = None, 0.0
        self.aliases = {fold(k): [fold(x) for x in v] for k, v in Config.APP_ALIASES.items()}

    @classmethod
    def _run(cls, cmd, timeout=15):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                               errors="ignore", **cls.NOWIN)
            return r.returncode, r.stdout
        except Exception:
            return 1, ""

    # ── descoberta dos aplicativos instalados ──
    def _scan_windows(self):
        rc, out = self._run(["powershell", "-NoProfile", "-Command",
                             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"], 30)
        data = json.loads(out) if out.strip() else []
        data = [data] if isinstance(data, dict) else data
        return [{"name": a["Name"], "launch": ["explorer.exe", "shell:AppsFolder\\" + a["AppID"]]}
                for a in data if a.get("Name") and a.get("AppID")]

    def _scan_mac(self):
        out = []
        for d in ("/Applications", "/Applications/Utilities", "/System/Applications", "/System/Applications/Utilities",
                  os.path.expanduser("~/Applications")):
            try:
                names = os.listdir(d)
            except OSError:
                continue
            out += [{"name": n[:-4], "launch": ["open", "-a", os.path.join(d, n)], "proc": n[:-4]}
                    for n in names if n.endswith(".app")]
        return out

    def _scan_linux(self):
        dirs = ["/usr/share/applications", "/usr/local/share/applications", os.path.expanduser("~/.local/share/applications"),
                "/var/lib/flatpak/exports/share/applications", os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
                "/var/lib/snapd/desktop/applications"]
        out = []
        for d in dirs:
            for path in glob.glob(os.path.join(d, "*.desktop")):
                name = loc = exec_ = None
                hidden, inside = False, False
                try:
                    with open(path, encoding="utf-8", errors="ignore") as f:
                        for ln in f:
                            ln = ln.strip()
                            if ln.startswith("["):
                                inside = ln == "[Desktop Entry]"
                            elif inside and "=" in ln:
                                k, v = ln.split("=", 1)
                                if k == "Name":
                                    name = v
                                elif k in ("Name[pt_BR]", "Name[pt]"):
                                    loc = v
                                elif k == "Exec":
                                    exec_ = v
                                elif (k in ("NoDisplay", "Hidden") and v.lower() == "true") or (k == "Type" and v != "Application"):
                                    hidden = True
                except OSError:
                    continue
                if hidden or not name or not exec_:
                    continue
                base = {"desktop": os.path.basename(path)[:-8], "exec": exec_}
                out.append({"name": name, **base})
                if loc and loc != name:
                    out.append({"name": loc, **base})
        return out

    def catalog(self):
        with self.lock:
            if self._cache is None or time.time() - self._t > 600:
                try:
                    apps = (self._scan_windows() if sys.platform.startswith("win")
                            else self._scan_mac() if sys.platform == "darwin" else self._scan_linux())
                except Exception:
                    apps = []
                apps += [{"name": k, "launch": v["open"], "proc": v.get("process")} for k, v in Config.CUSTOM_APPS.items()]
                self._cache, self._t = apps, time.time()
            return self._cache

    # ── interpretação do pedido ──
    @staticmethod
    def _score(en, n):
        if en == n:
            return 100
        if len(n) < 3:
            return 0
        if en.startswith(n + " "):
            return 85
        if f" {n} " in f" {en} ":
            return 75
        ratio = max([difflib.SequenceMatcher(None, en, n).ratio()] +
                    [difflib.SequenceMatcher(None, w, n).ratio() for w in en.split()])
        return 76 if ratio >= 0.85 else 0            # tolera erros de digitação ("crome")

    def resolve(self, query):
        q = re.sub(r"^(?:o|a|os|as) ", "", fold(query))
        if len(q) < 2:
            return None
        for n in self.aliases.get(q, [q]):           # apelidos são tentados na ordem de preferência
            best, score = None, 0
            for e in self.catalog():
                en = fold(e["name"])
                sc = self._score(en, n)
                if sc > score or (sc == score and best and len(en) < len(fold(best["name"]))):
                    best, score = e, sc
            if best and score >= 75:
                return best
        return None

    def plan(self, text):
        """Devolve {'action','items','force'} se o texto pede para abrir/fechar um app INSTALADO; senão None."""
        m = self.RX.search(text)
        if not m:
            return None
        action = "close" if fold(m.group("v")) in {fold(v) for v in self.CLOSE_V} else "open"
        items = []
        for part in re.split(r"\s+e\s+|\s*,\s*", self.NOISE.sub("", m.group("t"))):
            part = part.strip()
            entry = self.resolve(part) if part else None
            if entry and all(i["entry"] is not entry for i in items):
                items.append({"entry": entry, "query": part})
        return {"action": action, "items": items, "force": bool(self.FORCE.search(text))} if items else None

    # ── abrir ──
    @staticmethod
    def _launch_cmd(e):
        if e.get("launch"):
            return e["launch"]
        if shutil.which("gtk-launch"):
            return ["gtk-launch", e["desktop"]]
        return shlex.split(re.sub(r"%[a-zA-Z%]", "", e["exec"]))

    def open(self, e):
        spawn(self._launch_cmd(e))
        return f"abrir '{e['name']}': comando de abertura enviado."

    # ── fechar (sempre de forma graciosa; 'force' só se o usuário pedir) ──
    def _close_windows(self, e, hint, force):
        rc, out = self._run(["powershell", "-NoProfile", "-Command",
                             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Process | Where-Object {$_.MainWindowTitle} | "
                             "Select-Object Id,ProcessName,MainWindowTitle | ConvertTo-Json -Compress"], 20)
        procs = json.loads(out) if out.strip() else []
        procs = [procs] if isinstance(procs, dict) else procs
        names = {fold(e["name"]), fold(hint)}
        if e.get("proc"):
            names.add(fold(re.sub(r"\.exe$", "", e["proc"], flags=re.I)))
        names.discard("")
        ids, blocked = set(), False
        for p in procs:
            pn, title = fold(p.get("ProcessName", "")), fold(p.get("MainWindowTitle", ""))
            hit = any(pn == n or pn == n.replace(" ", "") or (len(pn) >= 3 and pn in n.split())
                      or title == n or title.endswith(" " + n) for n in names)
            if not hit:
                continue
            if protected(p.get("ProcessName", "")) or p.get("Id") == os.getpid():
                blocked = True
                continue
            ids.add(int(p["Id"]))
        if not ids:
            return f"fechar '{e['name']}': " + ("bloqueado por segurança." if blocked else "não está em execução (nenhuma janela aberta).")
        cmd = "; ".join(f"Stop-Process -Id {i} -Force -ErrorAction SilentlyContinue" if force else
                        f"(Get-Process -Id {i} -ErrorAction SilentlyContinue).CloseMainWindow() | Out-Null" for i in sorted(ids))
        self._run(["powershell", "-NoProfile", "-Command", cmd], 20)
        return self._closed(e, force)

    def _close_mac(self, e, hint, force):
        rc, out = self._run(["osascript", "-e", 'tell application "System Events" to get name of every process whose background only is false'])
        running = [x.strip() for x in out.split(",") if x.strip()]
        targets = {fold(e["name"]), fold(hint), fold(e.get("proc") or "")} - {""}
        name = next((r for r in running if fold(r) in targets), None)
        if not name:
            return f"fechar '{e['name']}': não está em execução."
        if protected(name) or not re.fullmatch(r"[\w .&+()\-]+", name):
            return f"fechar '{e['name']}': bloqueado por segurança."
        self._run(["pkill", "-x", name] if force else ["osascript", "-e", f'tell application "{name}" to quit'])
        return self._closed(e, force)

    @staticmethod
    def _linux_proc(exec_):
        toks = shlex.split(re.sub(r"%[a-zA-Z%]", "", exec_))
        while toks and (toks[0] == "env" or "=" in toks[0]):
            toks.pop(0)
        if not toks:
            return "bin", "", ""
        if os.path.basename(toks[0]) == "flatpak" and "run" in toks:
            rest = [t for t in toks[toks.index("run") + 1:] if not t.startswith("-")]
            return "flatpak", rest[0] if rest else "", ""
        return "bin", os.path.basename(toks[0]), toks[0]

    def _close_linux(self, e, hint, force):
        kind, proc, path = self._linux_proc(e["exec"]) if e.get("exec") else ("bin", e.get("proc") or e["name"], "")
        if not proc or protected(proc):
            return f"fechar '{e['name']}': bloqueado por segurança."
        sig = "-KILL" if force else "-TERM"
        if kind == "flatpak":
            ok = self._run(["flatpak", "kill", proc])[0] == 0
        elif self._run(["pgrep", "-x", proc[:15]])[0] == 0:
            self._run(["pkill", sig, "-x", proc[:15]])
            ok = True
        elif path and self._run(["pgrep", "-f", "^" + re.escape(path)])[0] == 0:
            self._run(["pkill", sig, "-f", "^" + re.escape(path)])
            ok = True
        else:
            ok = False
        return self._closed(e, force) if ok else f"fechar '{e['name']}': não está em execução."

    @staticmethod
    def _closed(e, force):
        return f"fechar '{e['name']}': " + ("encerrado à força." if force else
               "pedido de fechamento enviado (se houver arquivos não salvos, o programa pode pedir confirmação).")

    def close(self, e, hint, force):
        if protected(e["name"]) or protected(e.get("proc") or ""):
            return f"fechar '{e['name']}': bloqueado por segurança (programa essencial ou ligado ao próprio assistente)."
        if sys.platform.startswith("win"):
            return self._close_windows(e, hint, force)
        return self._close_mac(e, hint, force) if sys.platform == "darwin" else self._close_linux(e, hint, force)

    @staticmethod
    def _humanize(msg):
        m = re.match(r"(abrir|fechar) '(.+?)': (.*)", msg)
        if not m:
            return msg
        act, name, rest = m.groups()
        if act == "abrir":
            return f"Abri o {name}."
        if rest.startswith("não está em execução"):
            return f"O {name} não está em execução."
        if rest.startswith("bloqueado"):
            return f"Por segurança, não fecho o {name}."
        if rest.startswith("encerrado"):
            return f"Encerrei o {name} à força."
        if rest.startswith("pedido de fechamento"):
            return f"Pedi ao {name} que fechasse. Se houver arquivos não salvos, ele pode pedir confirmação."
        return msg

    def execute(self, plan):
        out = []
        for it in plan["items"]:
            name = it["entry"]["name"]
            try:
                out.append(self._humanize(self.open(it["entry"]) if plan["action"] == "open"
                                          else self.close(it["entry"], it["query"], plan["force"])))
            except Exception as ex:
                out.append(f"Não consegui {'abrir' if plan['action'] == 'open' else 'fechar'} o {name}: {ex}.")
        return " ".join(out)


# ── Controle do computador: pastas, sites e mensagens ───────────────────────
def spawn(cmd):
    """Inicia um programa desligado do assistente (não morre junto com ele)."""
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200          # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)


def proc_key(name):
    return fold(re.sub(r"\.exe$", "", os.path.basename(str(name)), flags=re.I))


class _Desktop:
    """Automação mínima de janelas e teclado. active() devolve (processo_normalizado, título da janela)."""
    @staticmethod
    def create():
        if sys.platform.startswith("win"):
            return _WinDesktop()
        return _MacDesktop() if sys.platform == "darwin" else _LinuxDesktop()


class _WinDesktop(_Desktop):
    """Windows, só com ctypes (nada para instalar)."""
    VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
          "down": 0x28, "up": 0x26, "backspace": 0x08, "space": 0x20}

    def __init__(self):
        import ctypes
        from ctypes import wintypes as wt
        self.ct, self.wt = ctypes, wt
        self.u, self.k = ctypes.windll.user32, ctypes.windll.kernel32
        u, k = self.u, self.k
        self.ENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        u.GetForegroundWindow.restype = wt.HWND
        u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
        u.IsWindowVisible.argtypes = [wt.HWND]
        u.IsIconic.argtypes = [wt.HWND]
        u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
        u.SetForegroundWindow.argtypes = [wt.HWND]
        u.EnumWindows.argtypes = [self.ENUM, wt.LPARAM]
        u.OpenClipboard.argtypes = [wt.HWND]
        u.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
        u.SetClipboardData.restype = wt.HANDLE
        u.GetClipboardData.argtypes = [wt.UINT]
        u.GetClipboardData.restype = wt.HANDLE
        k.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
        k.GlobalAlloc.restype = wt.HGLOBAL
        k.GlobalLock.argtypes = [wt.HGLOBAL]
        k.GlobalLock.restype = wt.LPVOID
        k.GlobalUnlock.argtypes = [wt.HGLOBAL]
        k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k.OpenProcess.restype = wt.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
        k.CloseHandle.argtypes = [wt.HANDLE]

    def _title(self, h):
        buf = self.ct.create_unicode_buffer(512)
        self.u.GetWindowTextW(h, buf, 512)
        return buf.value

    def _proc(self, h):
        pid = self.wt.DWORD()
        self.u.GetWindowThreadProcessId(h, self.ct.byref(pid))
        handle = self.k.OpenProcess(0x1000, False, pid.value)       # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        buf, size = self.ct.create_unicode_buffer(520), self.wt.DWORD(520)
        ok = self.k.QueryFullProcessImageNameW(handle, 0, buf, self.ct.byref(size))
        self.k.CloseHandle(handle)
        return proc_key(buf.value) if ok else ""

    def active(self):
        h = self.u.GetForegroundWindow()
        return (self._proc(h), self._title(h)) if h else ("", "")

    def _windows(self, proc):
        found = []

        def cb(h, _):
            if self.u.IsWindowVisible(h) and self._title(h) and self._proc(h) == proc:
                found.append(h)
            return True
        self.u.EnumWindows(self.ENUM(cb), 0)
        return found

    def focus(self, proc, name=""):
        for h in self._windows(proc):
            if self.u.IsIconic(h):
                self.u.ShowWindow(h, 9)                              # SW_RESTORE
            self.u.keybd_event(0x12, 0, 0, 0)                        # toque em Alt: o Windows libera o SetForegroundWindow
            self.u.keybd_event(0x12, 0, 2, 0)
            self.u.SetForegroundWindow(h)
            time.sleep(0.4)
            if self.active()[0] == proc:
                return True
        return False

    def hotkey(self, combo):
        keys = [self.VK.get(p) or ord(p.upper()) for p in combo.lower().replace("mod", "ctrl").split("+")]
        for v in keys:
            self.u.keybd_event(v, 0, 0, 0)
            time.sleep(0.02)
        for v in reversed(keys):
            self.u.keybd_event(v, 0, 2, 0)

    def _get_clip(self):
        if not self.u.OpenClipboard(None):
            return None
        try:
            h = self.u.GetClipboardData(13)                          # CF_UNICODETEXT
            if not h:
                return None
            ptr = self.k.GlobalLock(h)
            text = self.ct.wstring_at(ptr)
            self.k.GlobalUnlock(h)
            return text
        finally:
            self.u.CloseClipboard()

    def _set_clip(self, text):
        data = (text + "\0").encode("utf-16-le")
        h = self.k.GlobalAlloc(0x0042, len(data))                    # GMEM_MOVEABLE | GMEM_ZEROINIT
        ptr = self.k.GlobalLock(h)
        self.ct.memmove(ptr, data, len(data))
        self.k.GlobalUnlock(h)
        for _ in range(20):
            if self.u.OpenClipboard(None):
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("não consegui acessar a área de transferência")
        try:
            self.u.EmptyClipboard()
            self.u.SetClipboardData(13, h)
        finally:
            self.u.CloseClipboard()

    def paste(self, text):
        """Cola via área de transferência (aceita acentos e emojis) e restaura o que havia nela."""
        old = self._get_clip()
        self._set_clip(text)
        self.hotkey("ctrl+v")
        time.sleep(0.3)
        if old is not None:
            self._set_clip(old)


class _MacDesktop(_Desktop):
    """macOS via osascript (exige permissão de Acessibilidade para o Terminal/Python)."""
    CODES = {"enter": 36, "tab": 48, "esc": 53, "down": 125, "up": 126, "backspace": 51, "space": 49}

    @staticmethod
    def _osa(script):
        return Apps._run(["osascript", "-e", script], 10)

    def active(self):
        _, name = self._osa('tell application "System Events" to get name of first process whose frontmost is true')
        _, title = self._osa('tell application "System Events" to tell (first process whose frontmost is true) to get name of front window')
        return fold(name), title.strip()

    def focus(self, proc, name=""):
        self._osa(f'tell application "{name}" to activate')
        time.sleep(0.8)
        return self.active()[0] == proc

    def hotkey(self, combo):
        parts = combo.lower().split("+")
        mods = ", ".join({"mod": "command", "ctrl": "control", "shift": "shift", "alt": "option"}[m] + " down" for m in parts[:-1])
        act = f"key code {self.CODES[parts[-1]]}" if parts[-1] in self.CODES else f'keystroke "{parts[-1]}"'
        self._osa(f'tell application "System Events" to {act}' + (f" using {{{mods}}}" if mods else ""))

    def paste(self, text):
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), timeout=5)
        self.hotkey("mod+v")
        time.sleep(0.3)


class _LinuxDesktop(_Desktop):
    """Linux em X11 via xdotool (no Wayland a automação de teclado é limitada)."""
    KEYS = {"enter": "Return", "esc": "Escape", "tab": "Tab", "down": "Down", "up": "Up", "backspace": "BackSpace", "mod": "ctrl"}

    def __init__(self):
        if not shutil.which("xdotool"):
            raise RuntimeError("no Linux é preciso instalar o xdotool (sudo apt install xdotool); só funciona em X11")

    @staticmethod
    def _x(*args):
        return Apps._run(["xdotool", *args], 10)

    def active(self):
        _, pid = self._x("getactivewindow", "getwindowpid")
        _, title = self._x("getactivewindow", "getwindowname")
        try:
            with open(f"/proc/{pid.strip()}/comm") as f:
                comm = f.read()
        except OSError:
            comm = ""
        return fold(comm), title.strip()

    def focus(self, proc, name=""):
        ids = self._x("search", "--onlyvisible", "--class", name or proc)[1].split()
        if ids:
            self._x("windowactivate", ids[-1])
            time.sleep(0.6)
        return self.active()[0] == proc

    def hotkey(self, combo):
        self._x("key", "+".join(self.KEYS.get(p, p) for p in combo.lower().split("+")))

    def paste(self, text):
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-b", "-i"]):
            if shutil.which(cmd[0]):
                subprocess.run(cmd, input=text.encode("utf-8"), timeout=5)
                break
        else:
            raise RuntimeError("instale xclip ou xsel para colar texto")
        self.hotkey("ctrl+v")
        time.sleep(0.3)


class Computer:
    """Pedidos que mexem no computador: abrir pasta, abrir site/vídeo, enviar mensagem em app."""
    OPEN_V = re.compile(r"\b(?:abr[ae]|abra|abrir|acesse|acessar|v[aá] (?:para|ao|à|pra)|ir para|navegue|me leve|entre (?:no|na)|"
                        r"toque|toca|tocar|coloque|coloca|ponha|reproduza|reproduzir|assista|quero (?:ver|assistir|ouvir))\b", re.I)
    _SEND = r"(?:envi\w*|mand\w*|escrev\w*|diz\w*|fal\w*|avis\w*)"
    _APPS = "|".join(map(re.escape, Config.MESSENGERS))
    MSG = re.compile(
        _SEND + r"\b.{0,40}?\b(?:mensagem|msg|dm|recado)\b|"
        r"\b(?:mensagem|msg|dm)\s+(?:para|pra|pro)\b|"
        + _SEND + r"\b.{0,80}?\b(?:para|pra|pro)\b.{0,60}?\b(?:no|na|pelo|pela|via)\s+(?:" + _APPS + r")\b|"
        r"\b(?:" + _APPS + r")\b.{0,40}?\b" + _SEND + r"\b.{0,60}?\b(?:para|pra|pro)\b", re.I)
    MSG_FALLBACK = re.compile(r"(?:para|pra|pro)\s+(?:o |a )?(?P<c>[\w.\-]+)\b.*?(?:\b(?:dizendo|falando|escrevendo|com (?:o )?texto|que)\b|:)\s*(?:que\s+)?:?\s*"
                              r"[\"“]?(?P<m>.+?)[\"”]?\s*$", re.I)
    MSG_SIMPLE = re.compile(
        r"\b(?:mand\w*|envi\w*|diz\w*|diga|fal\w*|escrev\w*|avis\w*)\s+(?:(?:um|uma)\s+)?(?P<m>.+?)\s+"
        r"(?:para|pra|pro)\s+(?:(?:o|a)\s+)?(?P<c>[\w.\-]+)", re.I)
    MSG_GENERIC = {"mensagem", "msg", "dm", "recado"}
    FOLDER = re.compile(r"\b(?:pasta|diret[oó]rio)\b|\b(?:explorador|gerenciador) de arquivos\s+(?:na|no|em|para|d[aeo])\b|"
                        r"\b(?:explorer|finder)\s+(?:na|no|em)\b", re.I)
    SITE = re.compile(r"\b(?:site|p[aá]gina|url|link|youtube|google|gmail|github|netflix|instagram|facebook|twitter|wikipedia|"
                      r"amazon|chatgpt|whatsapp web|v[ií]deo|canal|live)\b|\b[\w-]+\.(?:com|org|net|io|gov|edu|tv|me|dev|app|br)\b", re.I)
    KNOWN = {"imagens": "pictures", "imagem": "pictures", "fotos": "pictures", "pictures": "pictures", "downloads": "downloads",
             "download": "downloads", "documentos": "documents", "documents": "documents", "area de trabalho": "desktop",
             "desktop": "desktop", "videos": "videos", "musicas": "music", "musica": "music"}
    STRONG = ("downloads", "imagens", "fotos", "documentos", "area de trabalho")      # abrem pasta mesmo sem a palavra "pasta"
    STOP = {"pasta", "diretorio", "abra", "abre", "abrir", "explorador", "gerenciador", "arquivos", "de", "do", "da", "dos", "das",
            "na", "no", "em", "o", "a", "os", "as", "para", "pra", "minha", "meu", "meus", "minhas", "navegue", "ate", "ir", "va",
            "dentro", "que", "esta", "fica", "ficam", "onde", "tem", "mesma", "por", "favor", "arquivo", "documento", "foto",
            "imagem", "print", "planilha", "apresentacao", "pdf", "captura", "tela", "screenshot", "ultimo", "ultima", "recente",
            "mais", "novo", "nova", "baixado", "baixada", "rapidinho", "agora"}
    # arquivos (só no singular: "as imagens" é a pasta, "a imagem praia.png" é um arquivo)
    FILE_WORD = re.compile(r"\b(?:arquivo|documento|foto|imagem|print|captura(?: de tela)?|screenshot|planilha|apresenta[cç][aã]o|pdf)\b", re.I)
    EXT_RX = re.compile(r"\b[\w\-]+\.(?:pdf|docx?|xlsx?|pptx?|txt|csv|png|jpe?g|gif|bmp|webp|heic|mp[34]|mkv|avi|mov|zip|rar|7z|odt|rtf|md|json|exe|bat|ps1|msi|lnk)\b", re.I)
    IMG = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".heic")
    KINDS = {"foto": IMG, "imagem": IMG, "print": IMG, "captura": IMG, "screenshot": IMG, "planilha": (".xlsx", ".xls", ".csv", ".ods"),
             "apresentacao": (".pptx", ".ppt", ".odp"), "pdf": (".pdf",), "documento": (".pdf", ".doc", ".docx", ".txt", ".odt", ".rtf")}
    FILE_Q = re.compile(r"\b(?:arquivo|documento|foto|imagem|print|planilha|pdf|apresenta[cç][aã]o)\s+(?:d[aeo]s?\s+)?(?!pasta\b)"
                        r"(?P<q>[^,.;!?]+?)(?=\s+(?:na|no|em|n[ao]s|dentro|que|pasta|d[aeo]s?\s+pasta|por favor)\b|[,.;!?]|$)", re.I)
    TEMP_EXT = (".crdownload", ".part", ".tmp", ".download", ".partial")                # downloads incompletos
    BLOCKED_EXT = (".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta",
                   ".scr", ".lnk", ".reg", ".jar", ".dll", ".sh", ".appimage", ".app", ".command", ".pif", ".cpl")
    SPLIT = (re.compile(r"\s+(?:(?:que\s+)?(?:est[aá]|fica|ficam)\s+)?dentro\s+d[aeo]s?\s+", re.I),          # "X dentro de Y"
             re.compile(r"\s+(?:que\s+)?(?:est[aá]|fica|ficam)\s+(?:em|n[ao]s?)\s+", re.I))               # "X que está em/na Y"

    PATH_RX = re.compile(r'[A-Za-z]:\\[^\n"<>|?*]+|~[/\\][^\n"]*|(?<!\w)/(?=[\w~.])[^\n"<>|?*]+')
    SKIP_DIRS = {"appdata", "node_modules", "$recycle.bin", "system volume information", "windows", "program files"}

    def __init__(self, tools):
        self.tools = tools

    def _path_in(self, text):
        """Caminho de pasta que EXISTE dentro do texto (tolera palavras sobrando no fim)."""
        m = self.PATH_RX.search(text)
        cand = os.path.expanduser(m.group(0).strip().rstrip(".,;")) if m else ""
        while cand:
            if os.path.isdir(cand):
                return cand
            if " " not in cand:
                return None
            cand = cand.rsplit(" ", 1)[0].rstrip(".,;")
        return None

    # ── o que o usuário quer? ──
    def _file_in(self, text):
        """Caminho de ARQUIVO existente dentro do texto (tolera palavras sobrando no fim)."""
        m = self.PATH_RX.search(text)
        cand = os.path.expanduser(m.group(0).strip().rstrip(".,;")) if m else ""
        while cand:
            if os.path.isfile(cand):
                return cand
            if " " not in cand:
                return None
            cand = cand.rsplit(" ", 1)[0].rstrip(".,;")
        return None

    def intent(self, text):
        if self.MSG.search(text):
            return "message"
        opens = bool(self.OPEN_V.search(text))
        bare = not self.PATH_RX.sub("", text).strip(" ,.!?\"'")                  # a mensagem é só o caminho
        if self._file_in(text) and (opens or bare):
            return "file"
        if opens and (self.FILE_WORD.search(text) or self.EXT_RX.search(text)):
            return "file"
        looks_path = self._path_in(text) or re.search(r"(?<![\w/])(?:[A-Za-z]:\\|~[/\\])", text)
        if looks_path and (opens or bare):
            return "folder"                                                 # só colou o caminho: abre a pasta
        if opens:
            f = fold(text)
            if self.FOLDER.search(text) or any(re.search(rf"\b{k}\b", f) for k in self.STRONG):
                return "folder"
            if self.SITE.search(text):
                return "site"
        return None

    def plan(self, text):
        kind = self.intent(text)
        if not kind:
            raise ValueError("pedido não reconhecido")
        a = self.tools._llm_args(PC_PROMPT, text)
        g = lambda k, n=120: str(a.get(k) or "")[:n].strip()
        if kind == "file":
            return self.plan_file(text, a)
        if kind == "folder":
            path = self.resolve_folder(text, g("folder"))
            if not path:
                raise ValueError(f"não encontrei a pasta '{g('folder') or text}'")
            return {"kind": "folder", "path": path}
        if kind == "site":
            site, query, channel = g("site"), g("query"), g("channel")
            latest, play = bool(a.get("latest")), bool(a.get("play"))
            explicit = (re.search(r"https?://[^\s\"'<>]+", text) or
                        re.search(r"(?<![\w@])(?:[\w-]+\.)+(?:com|org|net|io|gov|edu|tv|me|dev|app|br)(?:/[^\s\"'<>]*)?", text))
            if explicit:
                site = explicit.group(0).rstrip(".,;!?)")
            if not site:
                m = self.SITE.search(text)
                site = "youtube" if (m and re.fullmatch(r"v[ií]deo|canal|live|youtube", m.group(0), re.I)) else (m.group(0) if m else "")
            rest = re.sub(r"(?i)\b(?:abr\w*|acess\w*|v[aá]|ir|para|pra|ao|à|o|a|os|as|no|na|em|youtube|site|p[aá]gina|me|leve|por favor)\b", " ", text)
            if "youtube" in fold(site) and not (query or channel) and rest.strip(" ?.!,"):   # pediu algo além do site: reaproveita o extrator do YouTube
                channel, query, latest = self.tools.youtube_args(text)
                play = play or bool(re.search(r"v[ií]deo|toque|toca|coloque|ponha|assista|reproduz|live", text, re.I))
                query = re.sub(r"(?i)^\s*(?:\b(?:toque|toca|tocar|coloque|coloca|ponha|reproduza|assista|abra|abre|abrir|quero (?:ver|assistir|ouvir))\b\s*)+"
                               r"(?:(?:a|o|as|os)\s+)?(?:(?:m[uú]sica|v[ií]deo|can[cç][aã]o|clipe)\s+)?", "", query).strip()
            if "youtube" in fold(site) and query and re.search(r"m[uú]sica|v[ií]deo|toc|assist|coloque|can[cç][aã]o|clipe", text, re.I):
                play = True
            if not site:
                raise ValueError("não entendi qual site abrir")
            return {"kind": "site", "site": site, "query": query, "channel": channel, "latest": latest, "play": play}
        # mensagem
        app = fold(g("app"))
        if app not in Config.MESSENGERS:
            app = next((k for k in Config.MESSENGERS if k in fold(text)), "")
        if not app:
            raise ValueError("não entendi em qual aplicativo enviar (suportados: " + ", ".join(Config.MESSENGERS) + ")")
        contact, message = g("contact", 60), g("message", 500)
        if contact and not self.tools._in_text(contact, text):
            contact = ""                                                    # nome inventado pelo modelo
        if message and not self.tools._in_text(message, text):
            message = ""                                                    # texto reescrito pelo modelo (ex.: "oi" -> "Olá")
        if not (contact and message):
            m = self.MSG_FALLBACK.search(text)
            if m:
                contact, message = contact or m.group("c"), message or m.group("m")
        if not (contact and message):                                       # fallback sem LLM: "mande um oi para X no discord"
            m = self.MSG_SIMPLE.search(text)
            if m and m.group("m").strip().lower() not in self.MSG_GENERIC:
                contact, message = contact or m.group("c"), message or m.group("m").strip()
        m = self.MSG_SIMPLE.search(text)
        if m and contact and fold(contact) in fold(m.group("c")):
            contact = m.group("c")                                          # modelo cortou o nome (koga -> koga_83044): usa o literal
        if contact and not self.tools._in_text(contact, text):
            contact = ""                                                    # nome inventado pelo modelo
        if message and not self.tools._in_text(message, text):
            message = ""
        if not contact or not message:
            raise ValueError("faltou o destinatário ou o texto da mensagem")
        return {"kind": "message", "app": app, "contact": contact, "message": message}

    def execute(self, plan, emit=lambda *a: None):
        if plan["kind"] == "folder":
            return self.open_folder(plan["path"])
        if plan["kind"] == "file":
            return self.open_file(plan)
        if plan["kind"] == "site":
            return self.open_site(plan)
        return self.send_message(plan, emit)

    # ── pastas ──
    @staticmethod
    def known_folder(key):
        home = os.path.expanduser("~")
        if sys.platform.startswith("win"):
            try:
                import winreg
                value = {"pictures": "My Pictures", "downloads": "{374DE290-123F-4565-9164-ACA4C16C65F1}", "documents": "Personal",
                         "desktop": "Desktop", "videos": "My Video", "music": "My Music"}[key]
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
                    return os.path.expandvars(winreg.QueryValueEx(k, value)[0])    # respeita OneDrive e pastas movidas
            except Exception:
                pass
        elif sys.platform != "darwin":
            out = Apps._run(["xdg-user-dir", key.upper() if key != "documents" else "DOCUMENTS"], 5)[1].strip()
            if out:
                return out
        names = {"pictures": "Pictures", "downloads": "Downloads", "documents": "Documents", "desktop": "Desktop",
                 "videos": "Movies" if sys.platform == "darwin" else "Videos", "music": "Music"}
        return os.path.join(home, names[key])

    def _words(self, s):
        return [w for w in fold(s).split() if w not in self.STOP and len(w) > 2]

    def _search_bases(self):
        bases = [self.known_folder(k) for k in ("downloads", "documents", "desktop", "pictures", "videos", "music")]
        bases += list(Config.FOLDERS.values()) + [os.path.expanduser("~")]
        return [b for b in dict.fromkeys(bases) if b and os.path.isdir(b)]

    def find_dir(self, bases, words, depth=3, limit=40000):
        """Busca em LARGURA (acha primeiro as pastas mais rasas). Nome exato vence; senão, o que contiver as palavras."""
        want, partial, seen = " ".join(words), None, 0
        queue = deque((b, 0) for b in bases)
        while queue and seen < limit:
            base, lvl = queue.popleft()
            try:
                entries = list(os.scandir(base))
            except OSError:
                continue
            for e in entries:
                try:
                    if e.name.startswith(".") or e.name.lower() in self.SKIP_DIRS or not e.is_dir():
                        continue
                except OSError:
                    continue
                seen += 1
                fn = fold(e.name)
                if fn == want:
                    return e.path
                if partial is None and all(w in fn for w in words):
                    partial = e.path
                if lvl + 1 < depth:
                    queue.append((e.path, lvl + 1))
        return partial

    def resolve_folder(self, text, name=""):
        """Caminho completo > pastas suas > "X dentro de Y" > pasta conhecida (+ subpasta citada) > busca pelo nome.
        A subpasta é deduzida do TEXTO inteiro; o nome extraído pelo LLM é só um reforço."""
        path = self._path_in(text)
        if path:
            return path
        m = re.search(r"(?<![\w/])(?:[A-Za-z]:\\|~[/\\])[^\n\"<>|?*]*", text)
        if m:                                                                # caminho completo que não existe: não adivinha
            raise ValueError(f"a pasta '{Apps.NOISE.sub('', m.group(0)).strip().rstrip('.,;')}' não existe")
        f = fold(text)
        for fname, fpath in Config.FOLDERS.items():
            if fold(fname) and re.search(rf"\b{re.escape(fold(fname))}\b", f) and os.path.isdir(fpath):
                return fpath
        for rx in self.SPLIT:                                                # "prints que está dentro de Imagens"
            parts = rx.split(text, maxsplit=1)
            if len(parts) == 2:
                parent = self.resolve_folder(parts[1])
                if not parent:
                    raise ValueError(f"não encontrei a pasta '{parts[1].strip()}'")
                child = self._words(parts[0]) or [w for w in self._words(name) if w not in self._words(parts[1])]
                if not child:
                    return parent
                found = self.find_dir([parent], child, depth=4)
                if found:
                    return found
                raise ValueError(f"não encontrei a pasta '{' '.join(child)}' dentro de {parent}")
        base = key = None
        for k in sorted(self.KNOWN, key=len, reverse=True):
            if re.search(rf"\b{k}\b", f):
                cand = self.known_folder(self.KNOWN[k])
                if cand and os.path.isdir(cand):
                    base, key = cand, k
                    break
        if base:
            child = [w for w in self._words(f) if w not in key.split()]
            if not child:
                return base
            for ws in (child, [w for w in self._words(name) if w not in key.split()]):
                found = self.find_dir([base], ws, depth=4) if ws else None
                if found:
                    return found
            raise ValueError(f"não encontrei a pasta '{' '.join(child)}' dentro de {base}")
        for ws in (self._words(name), self._words(f)):
            found = self.find_dir(self._search_bases(), ws, depth=3) if ws else None
            if found:
                return found
        return None

    # ── arquivos dentro das pastas ──
    def find_file(self, bases, query, exts, depth=3, limit=40000):
        """Busca em largura. Nome exato > nome sem extensão > contém as palavras; empate: o mais recente."""
        qf = fold(query)
        words = [w for w in qf.split() if w not in self.STOP]
        cands, seen = [], 0
        queue = deque((b, 0) for b in bases)
        while queue and seen < limit:
            base, lvl = queue.popleft()
            try:
                entries = list(os.scandir(base))
            except OSError:
                continue
            for e in entries:
                try:
                    if e.name.startswith(".") or e.name.lower() in self.SKIP_DIRS:
                        continue
                    if e.is_dir():
                        if lvl + 1 < depth:
                            queue.append((e.path, lvl + 1))
                        continue
                except OSError:
                    continue
                seen += 1
                low = e.name.lower()
                if low.endswith(self.TEMP_EXT) or low in ("desktop.ini", "thumbs.db") or (exts and not low.endswith(exts)):
                    continue
                if query:
                    fn, stem = fold(e.name), fold(os.path.splitext(e.name)[0])
                    score = 3 if low == query.lower() else 2 if qf in (fn, stem) else 1 if words and all(w in fn for w in words) else 0
                    if not score:
                        continue
                else:
                    score = 1
                try:
                    mtime = e.stat().st_mtime
                except OSError:
                    mtime = 0
                cands.append((score, mtime, e.path))
        if not cands:
            return None, 0
        return max(cands, key=lambda c: (c[0], c[1]))[2], len(cands)

    def plan_file(self, text, a):
        fp = self._file_in(text)
        if fp:
            return {"kind": "file", "path": fp, "count": 1}
        g = lambda k, n=120: str(a.get(k) or "")[:n].strip()
        query = g("file")
        if query and not self.tools._in_text(query, text):
            query = ""                                                      # nome inventado pelo modelo
        if not query:
            m = self.EXT_RX.search(text)
            query = m.group(0) if m else ""
        if not query:
            m = self.FILE_Q.search(text)
            query = " ".join(w for w in m.group("q").split() if fold(w) not in self.STOP) if m else ""
        latest = bool(a.get("latest")) or bool(re.search(r"[uú]ltim|recente|mais novo|\bnovo\b|baixad", text, re.I))
        f = fold(text)
        exts = next((e for k, e in self.KINDS.items() if re.search(rf"\b{k}\b", f)), None)
        if query and re.search(r"\.\w{2,5}$", query):
            exts = None                                                     # a extensão dita já filtra
        loc = re.sub(re.escape(query), " ", text, flags=re.I) if query else text
        folder = self.resolve_folder(self.FILE_WORD.sub(" ", loc), g("folder"))     # None: nenhuma pasta citada
        if not query and not latest:
            raise ValueError("diga o nome do arquivo ou peça o mais recente")
        if not folder and not query:
            if not re.search(r"baix", text, re.I):
                raise ValueError("em qual pasta devo procurar o arquivo mais recente?")
            folder = self.known_folder("downloads")
        path, n = self.find_file([folder] if folder else self._search_bases(), query, exts, depth=3 if query else 1)
        if not path:
            raise ValueError(f"não encontrei o arquivo '{query or 'mais recente'}' " + (f"em {folder}" if folder else "nas pastas principais"))
        return {"kind": "file", "path": path, "count": n}

    def open_file(self, plan):
        path, ext = plan["path"], os.path.splitext(plan["path"])[1].lower()
        if ext in self.BLOCKED_EXT and not Config.ALLOW_EXECUTABLES:
            raise ValueError(f"por segurança não abro executáveis nem scripts ({os.path.basename(path)})")
        if hasattr(os, "startfile"):
            os.startfile(path)
        else:
            spawn(["open" if sys.platform == "darwin" else "xdg-open", path])
        extra = f" Havia {plan['count']} correspondências; abri a que melhor combina (em empate, a mais recente)." if plan.get("count", 1) > 1 else ""
        return f"Abri o arquivo {os.path.basename(path)}, da pasta {os.path.dirname(path)}.{extra}"

    def open_folder(self, path):
        spawn(["explorer.exe", path] if sys.platform.startswith("win") else ["open", path] if sys.platform == "darwin" else ["xdg-open", path])
        return f"Abri a pasta {path}."

    # ── sites e vídeos ──
    def youtube_url(self, channel, query, latest, play):
        watch = lambda vid: "https://www.youtube.com/watch?v=" + vid
        yt = YouTube(self.tools.rd())
        try:
            if channel:
                cid = yt.find_channel(channel)[0]
                if cid and play and (latest or not query):
                    feed = yt.feed(cid, 1)
                    if feed:
                        return watch(feed[0]["id"])
                if cid and play and query:
                    vids = yt.search_videos(f"{channel} {query}")
                    mine = [v for v in vids if v["channel_id"] == cid] or vids
                    if mine:
                        return watch(mine[0]["id"])
                if cid and not query:
                    return "https://www.youtube.com/channel/" + cid
            elif query and play:
                vids = yt.search_videos(query, recent=latest)
                if vids:
                    return watch(vids[0]["id"])
        except Exception:
            pass
        terms = f"{channel} {query}".strip()
        return Config.SEARCH_SITES["youtube"].format(q=urllib.parse.quote_plus(terms)) if terms else Config.SITES["youtube"]

    def site_url(self, p):
        site, q, f = p["site"], p["query"], fold(p["site"])
        if re.match(r"https?://", site, re.I):                               # endereço dito explicitamente: vai direto
            return site
        if re.fullmatch(r"[\w-]+(?:\.[\w-]+)+(?:/\S*)?", site):
            return "https://" + site
        if "youtube" in f:
            return self.youtube_url(p["channel"], q, p["latest"], p["play"])
        if q:
            for name, tpl in Config.SEARCH_SITES.items():
                if fold(name) in f:
                    return tpl.format(q=urllib.parse.quote_plus(q))
        for name, url in Config.SITES.items():
            if fold(name) in f:
                return url
        try:                                                                # site desconhecido: o 1º resultado de "<nome> site oficial"
            results = WebSearch().search(f"{site} site oficial")
            if results:
                return results[0]["url"]
        except Exception:
            pass
        return Config.SEARCH_SITES["google"].format(q=urllib.parse.quote_plus(site))

    def open_site(self, p):
        url = self.site_url(p)
        if not re.match(r"https?://", url, re.I):
            raise ValueError("endereço inválido")
        webbrowser.open(url, new=2)
        what = ("o vídeo no YouTube" if "youtube.com/watch" in url else "o canal no YouTube" if "youtube.com/channel" in url
                else "a página no navegador")
        return f"Abri {what}: {url}"

    # ── mensagens (automação de teclado) ──
    def send_message(self, plan, emit):
        rc, d = Config.MESSENGERS[plan["app"]], Config.UI_DELAY
        proc, contact, name = fold(rc["process"]), plan["contact"], rc["name"]
        ct = Config.CONTACTS.get(fold(contact), {})
        search, check = ct.get("search", contact), ct.get("title", contact)   # o que digitar na busca / o que aparece no título
        desk = _Desktop.create()
        emit("status", f"Abrindo o {name}...")
        if not desk.focus(proc, name):
            entry = self.tools.apps.resolve(name)
            if not entry:
                raise RuntimeError(f"o {name} não foi encontrado entre os aplicativos instalados")
            self.tools.apps.open(entry)
            for _ in range(30):
                time.sleep(1)
                if desk.focus(proc, name):
                    break
            else:
                raise RuntimeError(f"não consegui trazer o {name} para a frente")
            time.sleep(5 * d)                                               # carregamento inicial do app
        time.sleep(0.5 * d)
        emit("status", f"Procurando {contact}...")
        desk.hotkey(rc["switch"])                                           # seletor rápido de conversas
        time.sleep(0.7 * d)
        desk.paste(rc.get("prefix", "") + search)
        time.sleep(1.2 * d)
        desk.hotkey("enter")
        time.sleep(1.2 * d)
        cur, title = desk.active()
        if cur != proc:
            desk.hotkey("esc")
            raise RuntimeError(f"a janela do {name} perdeu o foco; cancelei antes de escrever")
        if Config.VERIFY_RECIPIENT and not any(w in fold(title) for w in fold(check).split() if len(w) >= 3):
            desk.hotkey("esc")
            raise RuntimeError(f"não consegui confirmar que a conversa com {contact} abriu (janela atual: '{title}'). Cancelei antes "
                               "de escrever. Se o nome exibido no app é diferente, cadastre em Config.CONTACTS; se o título nunca mostra o nome, "
                               "desative Config.VERIFY_RECIPIENT")
        emit("status", "Escrevendo a mensagem...")
        desk.paste(plan["message"])
        time.sleep(0.3 * d)
        if Config.SEND_MODE == "draft":
            return f"Digitei a mensagem para {contact} no {name}, mas não enviei (modo rascunho). Aperte Enter para enviar."
        if desk.active()[0] != proc:
            raise RuntimeError("o foco saiu do app antes de enviar; não enviei")
        desk.hotkey("enter")
        return f"Enviei a mensagem para {contact} no {name}: “{plan['message']}”."


# ── Despachante de ferramentas ──────────────────────────────────────────────
class Tools:
    YT = re.compile(r"youtube|\byt\b|\bcanal\b|youtuber|(?:[uú]ltim[oa]|mais recente|mais novo|novo|nova)\s+"
                    r"(?:v[ií]deo|live|epis[oó]dio|clipe)", re.I)
    WX = re.compile(r"previs[aã]o do tempo|\bclima\b|vai (?:chover|fazer (?:frio|calor|sol))|\bchover\b|\bchuva\b|"
                    r"temperatura|guarda-chuva|tempo (?:hoje|amanh[aã]|agora|nesta|nessa|esta|essa|na semana|"
                    r"no fim de semana|em |para )|como (?:est[aá]|vai estar|vai ficar|fica) o tempo|faz (?:frio|calor)|"
                    r"umidade do ar|\bgeada\b|\bgranizo\b", re.I)

    def __init__(self, ollama):
        self.ollama = ollama
        self._rd = None
        self.apps = Apps()
        self.pc = Computer(self)
        self.allow_apps = True          # o Assistant desliga para pedidos que não vêm do próprio computador

    def rd(self):
        return self._rd or PageReader(WebSearch.UA)

    def detect(self, text):
        pc = self.pc.intent(text) if (Config.COMPUTER_ENABLED and self.allow_apps) else None
        if pc in ("message", "folder", "file"):
            return "computer"
        if Config.APPS_ENABLED and self.allow_apps and self.apps.plan(text):
            return "apps"                # só se o app citado realmente estiver instalado
        if pc == "site":
            return "computer"
        if self.YT.search(text):
            return "youtube"
        if self.WX.search(text):
            return "weather"
        return None

    def _llm_args(self, system, text):
        m = Config.MODELS["manager"]
        try:
            raw = self.ollama.chat(m["name"], [{"role": "system", "content": system}, {"role": "user", "content": text}],
                                   options={"temperature": 0, "num_ctx": 2048}, keep_alive=m["keep_alive"], fmt="json")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _in_text(value, text):
        """Protege contra o modelo pequeno inventar um nome que o usuário não disse."""
        v, t = fold(value), fold(text)
        return bool(v) and (v in t or any(w in t.split() or w in t for w in v.split() if len(w) > 2))

    def weather_location(self, text):
        loc = str(self._llm_args(WX_PROMPT, text).get("location") or "")[:60].strip()
        if loc and not self._in_text(loc.split(",")[0], text):
            loc = ""
        if not loc:
            m = re.search(r"(?i:\b(?:em|para|de|na|no|do|da))\s+([A-ZÀ-Ú][\wÀ-ú'\-]*(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ú][\wÀ-ú'\-]*)*)", text)
            loc = m.group(1) if m and m.group(1).lower() not in ("hoje", "amanhã", "agora") else ""
        return loc or Config.DEFAULT_LOCATION

    def youtube_args(self, text):
        a = self._llm_args(YT_PROMPT, text)
        ch = str(a.get("channel") or "")[:80].strip()
        q = str(a.get("query") or "")[:120].strip()
        latest = bool(a.get("latest")) or bool(re.search(r"[uú]ltim|recente|mais novo|\bnovo\b|\bsaiu\b", text, re.I))
        if ch and not self._in_text(ch, text):
            ch = ""
        if not ch and not q:                                       # plano B sem LLM
            m = (re.search(r"(?i:canal|youtuber)\s+(?:d[oae]s?\s+)?(@?[\w.\-À-ú ]+?)(?=\s+(?i:no youtube|sobre|que)|[?.!,]|$)", text)
                 or re.search(r"(?i:v[ií]deo|live|clipe|epis[oó]dio)\s+(?:(?i:mais recente|recente|novo)\s+)?d[oae]s?\s+"
                              r"(@?[\w.\-À-ú ]+?)(?=\s+(?i:no youtube|sobre|que)|[?.!,]|$)", text))
            ch = m.group(1).strip() if m else ""
            if not ch:
                q = re.sub(r"(?i)\b(me|ach[ae]|procure|busque|mostra|mostre|encontre|quero|qual|um|uns|no youtube|youtube|v[ií]deos?)\b",
                           "", text)
                q = re.sub(r"^(de|sobre|do|da)\s+", "", re.sub(r"\s+", " ", q).strip(" ?.!"), flags=re.I)
        return ch, q, latest

    def run(self, name, text):
        """Devolve (texto, [urls]). Lança exceção se falhar (o chamador cai para a busca na web)."""
        if name == "apps":
            plan = self.apps.plan(text)
            if not plan:
                raise ValueError("aplicativo não encontrado")
            return self.apps.execute(plan), []
        if name == "weather":
            return Weather(self.rd()).report(self.weather_location(text))
        if name == "youtube":
            ch, q, latest = self.youtube_args(text)
            return YouTube(self.rd()).run(ch, q, latest)
        raise ValueError("ferramenta desconhecida")


class WebSearch:
    UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

    @staticmethod
    def _clean(s):
        return htmllib.unescape(re.sub(r"<[^>]+>", "", s)).strip()

    def _get(self, url, data=None):
        req = urllib.request.Request(url, data=data, headers={
            "User-Agent": self.UA, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5"})
        return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")

    # ── motores (tentados em ordem; o primeiro que devolver resultados vence) ──
    def _ddg_url(self, href):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(htmllib.unescape(href)).query)
        return qs["uddg"][0] if "uddg" in qs else htmllib.unescape(href)

    def _ddg(self, q):
        page = self._get("https://html.duckduckgo.com/html/",
                         urllib.parse.urlencode({"q": q, "kl": "br-pt"}).encode())
        links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.S)
        snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|td)>', page, re.S)
        return [(self._ddg_url(h), self._clean(t), self._clean(snips[i]) if i < len(snips) else "")
                for i, (h, t) in enumerate(links)]

    def _ddg_lite(self, q):
        page = self._get("https://lite.duckduckgo.com/lite/",
                         urllib.parse.urlencode({"q": q, "kl": "br-pt"}).encode())
        links = re.findall(r'<a[^>]*href="([^"]+)"[^>]*class=.result-link.[^>]*>(.*?)</a>', page, re.S)
        snips = re.findall(r'class=.result-snippet.[^>]*>(.*?)</td>', page, re.S)
        return [(self._ddg_url(h), self._clean(t), self._clean(snips[i]) if i < len(snips) else "")
                for i, (h, t) in enumerate(links)]

    @staticmethod
    def _bing_url(href):
        href = htmllib.unescape(href)
        u = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("u", [""])[0]
        if u.startswith("a1"):
            try:
                return base64.urlsafe_b64decode(u[2:] + "=" * (-len(u[2:]) % 4)).decode()
            except Exception:
                pass
        return href

    def _bing(self, q):
        page = self._get("https://www.bing.com/search?" +
                         urllib.parse.urlencode({"q": q, "setlang": "pt-BR", "cc": "BR"}))
        out = []
        for b in re.findall(r'<li class="b_algo".*?</li>', page, re.S):
            m = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
            sn = re.search(r'<p[^>]*>(.*?)</p>', b, re.S)
            if m:
                out.append((self._bing_url(m.group(1)), self._clean(m.group(2)),
                            self._clean(sn.group(1)) if sn else ""))
        return out

    def search(self, query):
        if HEURISTIC_WEB.search(query) and not re.search(r"\b20\d\d\b", query):
            query += f" {datetime.now().year}"   # ajuda a trazer resultados recentes
        for engine in (self._ddg, self._bing, self._ddg_lite):
            try:
                found = [r for r in engine(query) if r[0].startswith("http")][:Config.WEB_RESULTS]
                if found:
                    return [{"url": u, "title": t, "snippet": s} for u, t, s in found]
            except Exception:
                continue
        raise RuntimeError("nenhum mecanismo de busca respondeu")

    def context(self, query):
        """Retorna (texto_para_o_modelo, lista_de_fontes). Combina API estruturada + páginas."""
        reader = PageReader(self.UA)
        blocks, sources = [], []
        prov = Providers.lookup(query, reader.get_json)
        if prov:
            blocks.append(prov[0])
            sources += prov[1]
        try:
            results = self.search(query)
        except Exception:
            if not prov:
                raise
            results = []

        top = results[:Config.WEB_PAGES + 2]
        with ThreadPoolExecutor(max_workers=4) as ex:       # lê as páginas em paralelo
            pages = list(ex.map(reader.text, [r["url"] for r in top]))
        good = [i for i, t in enumerate(pages) if len(t) >= 300]
        if not good and not prov:                           # tudo vazio: provável página 100% JavaScript
            for i in range(min(2, len(top))):
                t = reader.render(top[i]["url"])
                if len(t) >= 300:
                    pages[i] = t
                    good.append(i)
                    break
        keep = set(good[:Config.WEB_PAGES])
        for i, r in enumerate(results):
            body = pages[i] if i in keep else ""
            blocks.append(f"[{i + 1}] {r['title']}\nURL: {r['url']}\n{r['snippet']}\n{body}".strip())
            sources.append(r["url"])
        return "\n\n".join(blocks), sources


# ════════════════════════════════════════════════════════════════════════════
# 6. ROUTER  (o modelo gerente decide quem responde)
# ════════════════════════════════════════════════════════════════════════════
class Router:
    def __init__(self, ollama, tools):
        self.ollama = ollama
        self.tools = tools

    def forced(self, text):
        for prefix, route in Config.FORCE_PREFIXES.items():
            if text.lower().startswith(prefix):
                return {"route": route, "web": route == "knowledge", "query": "",
                        "forced": True}, text[len(prefix):].strip() or text
        return None, text

    def adjust(self, d, text):
        """Regras determinísticas que corrigem o roteador pequeno."""
        if not d.get("forced") and (MEM_QUERY.search(text) or MEM_EXPLICIT.search(text)):
            d.update(route="chat", web=False, memory=True)      # papo sobre a memória: sem busca nem ferramentas
        elif not d.get("forced") and d["route"] != "reasoning":
            tool = self.tools.detect(text)
            if tool:                                            # apps / YouTube / clima: dados reais
                d.update(route=Config.TOOL_ROUTES.get(tool, "knowledge"), web=False, tool=tool)
        if d["route"] == "knowledge" and Config.WEB_ALWAYS_FOR_KNOWLEDGE and not d.get("tool"):
            d["web"] = True
        if (d["route"] == "chat" and not d.get("memory") and not d.get("tool")
                and HEURISTIC_WEB.search(text) and HEURISTIC_QUESTION.search(text)):
            d["route"], d["web"] = "knowledge", True
        d["query"] = (d.get("query") or text) if d["web"] else ""
        return d

    def heuristic(self, text):
        if HEURISTIC_REASONING.search(text):
            return {"route": "reasoning", "web": False, "query": ""}
        if HEURISTIC_WEB.search(text) or HEURISTIC_KNOWLEDGE.search(text):
            return self.adjust({"route": "knowledge", "web": True, "query": text}, text)
        return self.adjust({"route": "chat", "web": False, "query": ""}, text)

    def decide(self, text):
        forced, text = self.forced(text)
        if forced:
            return forced, text
        m = Config.MODELS["manager"]
        try:
            raw = self.ollama.chat(
                m["name"], [{"role": "system", "content": ROUTER_PROMPT},
                            {"role": "user", "content": text}],
                options={"temperature": 0.1, "num_ctx": 2048}, keep_alive=m["keep_alive"], fmt="json")
            data = json.loads(raw)
            if data.get("route") not in Config.ROUTES:
                raise ValueError("rota inválida")
            data["web"] = bool(data.get("web"))
            return self.adjust(data, text), text
        except (urllib.error.URLError, urllib.error.HTTPError):
            raise
        except Exception:
            return self.heuristic(text), text


# ════════════════════════════════════════════════════════════════════════════
# 7. ASSISTANT  (orquestração)
# ════════════════════════════════════════════════════════════════════════════
class Assistant:
    def __init__(self):
        self.ollama = Ollama(Config.OLLAMA_URL)
        self.models = ModelManager(self.ollama)
        self.tools = Tools(self.ollama)
        self.router = Router(self.ollama, self.tools)
        self.web = WebSearch()
        self.memory = Memory(Config.MEMORY_FILE)
        self.pending = None             # envio de mensagem aguardando o 'sim' do usuário
        self.history = []
        self.lock = threading.Lock()   # um pedido por vez (GPU/RAM)

    def reset(self):
        self.history = []

    def _gather_web(self, query, emit):
        """Pesquisa e devolve (instruções_para_o_modelo, fontes)."""
        emit("status", "Pesquisando na web...")
        try:
            ctx, sources = self.web.context(query)
            if ctx:
                return WEB_INSTRUCTION + ctx, sources
        except Exception:
            pass
        emit("status", "A busca na web falhou.")
        return WEB_FAILED_NOTE, []

    def start_conversation(self, local=True):
        """Nova conversa: zera o contexto, LÊ o arquivo de memória do disco e devolve a saudação inicial."""
        self.history = []
        facts = self.memory.facts() if (Config.MEMORY_ENABLED and local) else []
        h = datetime.now().hour
        hello = "Bom dia" if h < 12 else "Boa tarde" if h < 18 else "Boa noite"
        fallback = f"{hello}, {Config.USER_TITLE}. Todos os sistemas em operação. Como posso ajudar?"
        if not facts:
            return {"greeting": fallback, "facts": 0}
        m = Config.MODELS["manager"]
        try:
            task = (f"Gere a saudação de início de conversa: UMA frase curta começando com '{hello}'. Se a memória "
                    f"disser o nome do usuário, use-o no lugar de '{Config.USER_TITLE}'. Não liste nem comente a memória, "
                    "não faça perguntas sobre ela e não invente nada. Termine oferecendo ajuda.")
            text = self.ollama.chat(
                m["name"], [{"role": "system", "content": persona_prompt(task, self.memory.prompt_block("", everything=True))},
                            {"role": "user", "content": "(início da conversa)"}],
                options={"temperature": 0.6, "num_ctx": 4096, "num_predict": 80}, keep_alive=m["keep_alive"]).strip()
            if not (5 < len(text) < 300):
                text = fallback
        except Exception:
            text = fallback
        return {"greeting": text, "facts": len(facts)}

    def _curate(self, text, emit, quiet=False):
        """O LFM decide o que vale guardar (ou esquecer) e o arquivo markdown é atualizado."""
        if not quiet:
            emit("status", "Atualizando memória...")
        m = Config.MODELS["manager"]
        try:
            raw = self.ollama.chat(
                m["name"], [{"role": "system", "content": CURATOR_PROMPT + "\n\nMEMÓRIA ATUAL:\n" +
                             (self.memory.prompt_block(text) or "(vazia)")}, {"role": "user", "content": text}],
                options={"temperature": 0.1, "num_ctx": 4096}, keep_alive=m["keep_alive"], fmt="json")
            data = json.loads(raw)
        except Exception:
            return ""
        saved = [f["fact"] for f in (data.get("remember") or [])[:4]
                 if isinstance(f, dict) and self.memory.add(f.get("category", "outros"), f.get("fact", ""))]
        forgot = []
        if MEM_EXPLICIT.search(text):          # só esquece se o usuário pediu, e só o que ele citou
            for needle in (data.get("forget") or [])[:3]:
                if isinstance(needle, str) and fold(needle) in fold(text):
                    forgot += self.memory.forget(needle)
        if not (saved or forgot):
            return ""
        emit("memory", {"saved": saved, "forgot": forgot})
        return ("O sistema acabou de atualizar a memória do usuário. " + (f"Guardou: {'; '.join(saved)}. " if saved else "")
                + (f"Esqueceu: {'; '.join(forgot)}. " if forgot else "") + "Confirme isso em uma frase curta.")

    def _confirmation(self, text):
        """Se há uma mensagem aguardando confirmação, interpreta o 'sim/não' do usuário."""
        pend, self.pending = self.pending, None
        if not pend or time.time() - pend["t"] > Config.CONFIRM_TIMEOUT:
            return None
        base = {"route": "chat", "web": False, "query": ""}
        if AFFIRM.match(text):
            return {**base, "tool": "computer", "confirmed": pend["plan"]}
        if DENY.match(text):
            return {**base, "say": f"Cancelado, {Config.USER_TITLE}. Nada foi enviado."}
        return None

    def _use_computer(self, text, emit, decision):
        """Pasta / site / mensagem. Mensagens pedem confirmação antes (Config.SEND_MODE)."""
        try:
            plan = decision.get("confirmed") or self.tools.pc.plan(text)
            if plan["kind"] == "message" and Config.SEND_MODE == "confirm" and not decision.get("confirmed"):
                self.pending = {"plan": plan, "t": time.time()}
                decision["say"] = (f"Vou enviar no {Config.MESSENGERS[plan['app']]['name']} para {plan['contact']}: "
                                   f"“{plan['message']}”. Confirma, {Config.USER_TITLE}?")
                return "", [], False
            emit("status", "Executando no computador...")
            result = self.tools.pc.execute(plan, emit)
        except Exception as e:
            err = str(e)
            decision["say"] = f"Não consegui, {Config.USER_TITLE}: {err}" + ("" if err.endswith(("?", ".", "!")) else ".")
            return "", [], False
        decision["say"] = result                    # texto literal: o LLM pequeno costumava distorcer o resultado
        return "", [], False

    def _use_tool(self, name, text, emit, decision=None):
        """Roda a ferramenta; se falhar, cai para a pesquisa na web (exceto apps)."""
        decision = decision if decision is not None else {}
        if name == "computer":
            return self._use_computer(text, emit, decision)
        emit("status", {"youtube": "Consultando o YouTube...", "weather": "Consultando a previsão do tempo...",
                        "apps": "Executando no computador..."}[name])
        err = ""
        try:
            res = self.tools.run(name, text)
            if res and res[0]:
                if name == "apps":
                    decision["say"] = res[0]
                    return "", [], False
                return TOOL_INSTRUCTION + res[0], res[1], False
        except Exception as e:
            err = str(e)
        if name == "apps":
            decision["say"] = f"Não consegui, {Config.USER_TITLE}: {err or 'falha ao executar a ação'}."
            return "", [], False
        emit("status", "Ferramenta indisponível; pesquisando na web...")
        extra, sources = self._gather_web(text + (" youtube" if name == "youtube" else ""), emit)
        return extra, sources, not sources

    def _run(self, text, decision, emit):
        """Executa uma rota. Devolve (resposta, fontes, busca_falhou, modelo)."""
        key = Config.ROUTES[decision["route"]]
        model = Config.MODELS[key]
        emit("route", {"route": decision["route"], "key": key, "label": model["label"], "web": decision["web"],
                       "tool": decision.get("tool", "")})

        extra, sources, failed = "", [], False
        if decision.get("tool"):
            extra, sources, failed = self._use_tool(decision["tool"], text, emit, decision)
        elif decision["web"]:
            extra, sources = self._gather_web(decision["query"] or text, emit)
            failed = not sources
        elif decision["route"] == "chat" and not decision.get("memory"):
            extra = CHAT_HINT

        if decision.get("say"):                      # resposta literal (ex.: pedido de confirmação): sem gastar um modelo
            emit("token", decision["say"])
            return decision["say"], sources, failed, model
        if decision.get("mem_note"):
            extra += "\n" + decision["mem_note"]
        mem = self.memory.prompt_block(text, everything=bool(decision.get("memory"))) if Config.MEMORY_ENABLED else ""
        self.models.prepare(key, emit)
        messages = [{"role": "system", "content": persona_prompt(extra, mem)}] + self.history \
                   + [{"role": "user", "content": text}]

        flt, answer, started, completed = ThinkFilter(), "", False, False
        free = Config.UNLOAD_HEAVY_AFTER_RESPONSE and key != "manager"
        try:
            # keep_alive=0 faz o Ollama tirar o modelo da RAM assim que a resposta termina
            for kind, piece in self.ollama.stream(model["name"], messages, model["options"],
                                                  0 if free else model["keep_alive"]):
                parts = flt.feed(piece) if kind == "text" else [(kind, piece)]
                for k, p in parts:
                    if not started:
                        emit("status", "Respondendo...")
                        started = True
                    answer += p if k == "text" else ""
                    emit("token" if k == "text" else "think", p)
            for k, p in flt.flush():
                answer += p if k == "text" else ""
                emit("token" if k == "text" else "think", p)
            completed = True
        finally:
            if free and not completed:      # interrompido (botão Parar/erro): força a saída da RAM
                self.ollama.unload(model["name"])
        return answer.strip(), sources, failed, model

    def handle(self, text, emit, local=True):
        with self.lock:
            t0 = time.time()
            self.tools.allow_apps = local
            try:
                emit("status", "Analisando pedido...")
                decision = self._confirmation(text)
                if decision is None:
                    decision, text = self.router.decide(text)
                if Config.MEMORY_ENABLED and MEM_EXPLICIT.search(text):      # "lembre que...": salva ANTES de responder
                    decision["mem_note"] = self._curate(text, emit)
                    decision["mem_done"] = True
                answer, sources, failed, model = self._run(text, decision, emit)

                # O gerente admitiu que não sabe? Descarta o rascunho e refaz com gemma + web.
                if (Config.ESCALATE_ON_UNCERTAINTY and decision["route"] == "chat"
                        and not decision.get("forced") and not decision.get("memory") and not decision.get("tool")
                        and UNCERTAIN.search(answer)):
                    emit("retract", None)
                    emit("status", "Sem certeza; consultando a web...")
                    decision = {"route": "knowledge", "web": True, "query": text}
                    answer, sources, failed, model = self._run(text, decision, emit)

                self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
                self.history = self.history[-Config.HISTORY_TURNS * 2:]
                emit("done", {"label": model["label"], "sources": sources, "web_failed": failed,
                              "unloaded": Config.UNLOAD_HEAVY_AFTER_RESPONSE and model is not Config.MODELS["manager"],
                              "seconds": round(time.time() - t0, 1)})
                if Config.MEMORY_ENABLED and not decision.get("mem_done") and MEM_CANDIDATE.search(text):
                    self._curate(text, emit, quiet=True)        # aprende em segundo plano, depois da resposta
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")
                if e.code == 404:
                    emit("error", "Modelo não encontrado no Ollama. Instale com: ollama pull <modelo>")
                else:
                    emit("error", f"Erro do Ollama ({e.code}): {body[:200]}")
            except urllib.error.URLError:
                emit("error", f"Não consegui contatar o Ollama em {Config.OLLAMA_URL}. Ele está em execução?")
            except RuntimeError as e:
                emit("error", f"Ollama: {e}")


# ════════════════════════════════════════════════════════════════════════════
# 8. UI  (CSS + HTML + JS)
# ════════════════════════════════════════════════════════════════════════════
CSS = r"""
:root{--c:#19e3ff;--c2:#0a7f95;--bg:#02080f;--panel:rgba(8,28,40,.62);--line:rgba(25,227,255,.28);
--txt:#cfefff;--dim:#6f9bad;--warn:#ffb020;--ok:#38ffb0;--err:#ff5d6c;--f:"Rajdhani","Segoe UI",system-ui,sans-serif;--fd:"Orbitron","Rajdhani",system-ui,sans-serif}
body[data-state=listening]{--c:#38ffb0}
body[data-state=thinking]{--c:#ffb020}
body[data-state=speaking]{--c:#7df3ff}
*{box-sizing:border-box;margin:0}
html,body{height:100%}
body{background:radial-gradient(ellipse at 50% 0,#07263a 0,var(--bg) 62%);color:var(--txt);font:500 17px/1.45 var(--f);
display:grid;grid-template-columns:300px 1fr;grid-template-rows:auto minmax(0,1fr) auto;height:100vh;height:100dvh;overflow:hidden}
body::before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.5;
background:linear-gradient(var(--line) 1px,transparent 1px) 0 0/48px 48px,linear-gradient(90deg,var(--line) 1px,transparent 1px) 0 0/48px 48px;
mask-image:radial-gradient(circle at 50% 40%,#000,transparent 75%);-webkit-mask-image:radial-gradient(circle at 50% 40%,#000,transparent 75%)}
header{grid-column:1/3;display:flex;align-items:center;justify-content:space-between;padding:14px 26px;border-bottom:1px solid var(--line);position:relative}
header h1{font:700 22px var(--fd);letter-spacing:.32em;color:var(--c);text-shadow:0 0 14px var(--c)}
#clock{font:500 20px var(--fd);color:var(--dim)}
aside{min-height:0;padding:22px 20px;border-right:1px solid var(--line);display:flex;flex-direction:column;gap:22px;position:relative;overflow-y:auto}
.reactor{position:relative;width:190px;height:190px;margin:8px auto 0;flex:none}
.reactor i{position:absolute;border-radius:50%}
.r1{inset:0;border:2px dashed var(--c);opacity:.55;animation:spin 18s linear infinite}
.r2{inset:16px;border:3px solid transparent;border-top-color:var(--c);border-bottom-color:var(--c);animation:spin 5s linear infinite reverse}
.r3{inset:38px;border:2px dotted var(--c);animation:spin 9s linear infinite}
.r4{inset:58px;border:1px solid var(--c);box-shadow:0 0 18px var(--c),inset 0 0 18px var(--c)}
.core{inset:72px;background:radial-gradient(circle,#fff 0,var(--c) 45%,transparent 74%);box-shadow:0 0 46px var(--c);animation:pulse 2.6s ease-in-out infinite}
body[data-state=thinking] .r2{animation-duration:1.2s}
body[data-state=thinking] .core{animation-duration:.8s}
body[data-state=listening] .core{animation-duration:1.1s}
body[data-state=speaking] .core{animation-duration:.5s}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{50%{transform:scale(.78);opacity:.7}}
#state{text-align:center;font:600 15px var(--fd);letter-spacing:.28em;color:var(--c)}
.chip{border:1px solid var(--line);background:var(--panel);padding:10px 12px;display:grid;grid-template-columns:1fr auto;gap:2px 8px;
clip-path:polygon(0 0,calc(100% - 12px) 0,100% 12px,100% 100%,12px 100%,0 calc(100% - 12px))}
.chip b{font:700 15px var(--fd);letter-spacing:.14em}
.chip small{color:var(--dim)}
.chip .st{grid-row:1/3;grid-column:2;align-self:center;font:600 12px var(--fd);color:var(--dim)}
.chip.loaded{border-color:var(--ok)} .chip.loaded .st{color:var(--ok)}
.chip.missing{border-color:var(--err)} .chip.missing .st{color:var(--err)}
.chip.active{box-shadow:0 0 18px var(--c);border-color:var(--c)}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin-top:auto}
button{font:600 15px var(--f);color:var(--c);background:transparent;border:1px solid var(--line);padding:8px 12px;cursor:pointer;transition:.2s}
button:hover,button:focus-visible{background:rgba(25,227,255,.14);box-shadow:0 0 12px var(--c);outline:none}
button.off{color:var(--dim)}
main{min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:24px 8vw 12px 28px;position:relative}
#chips{display:flex;flex-direction:column;gap:10px}
.msg{margin:0 0 20px;max-width:780px}
.msg .tag{font:600 13px var(--fd);letter-spacing:.2em;color:var(--dim);margin-bottom:4px}
.msg .bubble{white-space:pre-wrap;padding:12px 16px;border-left:3px solid var(--c);background:var(--panel)}
.msg.user{margin-left:auto}
.msg.user .tag{text-align:right}
.msg.user .bubble{border-left:0;border-right:3px solid var(--warn)}
.msg .note{font-size:14px;color:var(--dim);margin-top:6px}
.msg details{font-size:14px;color:var(--dim);margin-top:6px}
.msg details div{white-space:pre-wrap;max-height:160px;overflow:auto;margin-top:4px;opacity:.8}
.bubble code{background:rgba(25,227,255,.12);padding:0 5px}
.bubble a{color:var(--c);word-break:break-all}
.bubble pre{background:rgba(0,0,0,.45);border:1px solid var(--line);padding:10px;overflow-x:auto;margin:8px 0}
.cursor::after{content:"▌";color:var(--c);animation:blink 1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
footer{grid-column:2;padding:12px 8vw 20px 28px;display:flex;gap:10px}
#input{flex:1;background:var(--panel);border:1px solid var(--line);color:var(--txt);font:500 18px var(--f);padding:12px 16px;outline:none}
#input:focus{border-color:var(--c);box-shadow:0 0 16px rgba(25,227,255,.3)}
#mic.on{color:var(--ok);border-color:var(--ok);box-shadow:0 0 16px var(--ok)}
@media(max-width:860px){
 body{grid-template-columns:1fr;grid-template-rows:auto auto minmax(0,1fr) auto}
 header,footer{grid-column:1} aside{max-height:34vh;flex-direction:row;flex-wrap:wrap;border-right:0;border-bottom:1px solid var(--line);align-items:center}
 .reactor{width:96px;height:96px;margin:0}.r3,.r4{display:none}.core{inset:30px}#state{display:none}
 main{padding:16px} #chips{flex-direction:row;flex-wrap:wrap;flex:1 1 100%} footer{padding:10px 16px 16px} .chip{flex:1 1 140px}
}
dialog{background:#04141f;color:var(--txt);border:1px solid var(--c);box-shadow:0 0 30px rgba(25,227,255,.35);padding:20px;width:min(720px,94vw);margin:auto}
dialog::backdrop{background:rgba(2,8,15,.82)}
dialog h2{font:700 18px var(--fd);letter-spacing:.25em;color:var(--c)}
dialog p{color:var(--dim);font-size:14px;margin:4px 0 10px;word-break:break-all}
#memtext{width:100%;height:50vh;background:rgba(0,0,0,.4);border:1px solid var(--line);color:var(--txt);font:14px/1.5 ui-monospace,Consolas,monospace;padding:10px;resize:vertical;margin-bottom:12px}
@media(prefers-reduced-motion:reduce){*{animation-duration:0s!important}}
"""

HTML = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>__CSS__</style></head>
<body data-state="idle">
<header><h1>__NAME__</h1><div><span id="clock"></span></div></header>
<aside>
  <div class="reactor"><i class="r1"></i><i class="r2"></i><i class="r3"></i><i class="r4"></i><i class="core"></i></div>
  <div id="state">EM ESPERA</div>
  <div id="chips"></div>
  <div class="tools">
    <button id="voice" title="Respostas em voz alta">Voz: ligada</button>
    <button id="stop" title="Interromper">Parar</button>
    <button id="unload" title="Descarregar modelos da memória">Liberar RAM</button>
    <button id="mem" title="Ver e editar o que o assistente sabe sobre você">Memória</button>
    <button id="reset" title="Apagar o contexto da conversa atual">Nova conversa</button>
  </div>
</aside>
<main id="log"></main>
<footer>
  <button id="mic" title="Falar (Chrome/Edge)">Falar</button>
  <input id="input" autocomplete="off" placeholder="Diga algo, __TITLE__... (/lfm /gemma /deepseek forçam um modelo)">
  <button id="send">Enviar</button>
</footer>
<dialog id="memdlg">
  <h2>MEMÓRIA</h2>
  <p id="mempath"></p>
  <textarea id="memtext" spellcheck="false"></textarea>
  <div class="tools"><button id="memsave">Salvar</button><button id="memclose">Fechar</button></div>
</dialog>
<script>window.CFG=__CFG__;</script>
<script>__JS__</script>
</body></html>"""

JS = r"""
const $ = s => document.querySelector(s);
const log = $('#log'), input = $('#input'), mic = $('#mic');
const STATES = {idle:'EM ESPERA', listening:'OUVINDO', thinking:'PROCESSANDO', speaking:'FALANDO'};
let busy = false, stick = true, ctrl = null, ttsOn = true, rec = null, listening = false;

/* ── utilidades ─────────────────────────────────────────── */
const esc = t => t.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const md = t => esc(t)
  .replace(/```\w*\n?([\s\S]*?)```/g, '<pre>$1</pre>')
  .replace(/`([^`\n]+)`/g, '<code>$1</code>')
  .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
  .replace(/(https?:\/\/[^\s<)"]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
function setState(s){ document.body.dataset.state = s; $('#state').textContent = STATES[s]; }
function scroll(){ if (stick && log.lastElementChild) log.lastElementChild.scrollIntoView({block:'end'}); }
log.addEventListener('scroll', () => { stick = log.scrollHeight - log.scrollTop - log.clientHeight < 90; }, {passive:true});
setInterval(() => $('#clock').textContent = new Date().toLocaleTimeString('pt-BR'), 1000);

/* ── módulo: mensagens ──────────────────────────────────── */
function addMsg(role, text){
  const el = document.createElement('div'); el.className = 'msg ' + role;
  el.innerHTML = '<div class="tag"></div><div class="bubble"></div><div class="note"></div>';
  el.querySelector('.tag').textContent = role === 'user' ? CFG.title.toUpperCase() : CFG.name;
  const m = {el, tag: el.querySelector('.tag'), bubble: el.querySelector('.bubble'),
             note: el.querySelector('.note'), full: '', think: '', thinkEl: null};
  if (role === 'user') m.bubble.textContent = text; else m.bubble.classList.add('cursor');
  log.appendChild(el); scroll(); return m;
}

/* ── módulo: voz (TTS e STT) ────────────────────────────── */
function stopSpeech(){ if ('speechSynthesis' in window) speechSynthesis.cancel(); }
function speak(text){
  if (!ttsOn || !('speechSynthesis' in window) || !text.trim()) return;
  const clean = text.replace(/```[\s\S]*?```/g, ' código omitido. ').replace(/https?:\/\/\S+/g, ' (link na tela) ').replace(/[*`#_>]/g, '');
  const voice = speechSynthesis.getVoices().find(v => v.lang.toLowerCase().startsWith('pt'));
  const parts = clean.split(/(?<=[.!?])\s+/).filter(Boolean);
  parts.forEach((p, i) => {
    const u = new SpeechSynthesisUtterance(p);
    u.lang = 'pt-BR'; u.rate = 1.03; u.pitch = .85; if (voice) u.voice = voice;
    u.onstart = () => setState('speaking');
    if (i === parts.length - 1) u.onend = () => !busy && setState('idle');
    speechSynthesis.speak(u);
  });
}
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
function toggleMic(){
  if (!SR) return alert('Reconhecimento de voz não suportado. Use Chrome ou Edge.');
  if (listening) return rec.stop();
  stopSpeech(); rec = new SR(); rec.lang = 'pt-BR'; rec.interimResults = true;
  rec.onstart = () => { listening = true; setState('listening'); mic.classList.add('on'); };
  rec.onresult = e => {
    const t = [...e.results].map(r => r[0].transcript).join('');
    input.value = t; if (e.results[e.results.length - 1].isFinal) send(t);
  };
  rec.onend = () => { listening = false; mic.classList.remove('on'); if (!busy) setState('idle'); };
  rec.start();
}

/* ── módulo: painel de modelos ──────────────────────────── */
function buildChips(){
  $('#chips').innerHTML = CFG.models.map(m =>
    `<div class="chip" id="chip-${m.key}"><b>${m.label}</b><span class="st">—</span><small>${m.name} · ${m.role}</small></div>`
  ).join('');
}
async function poll(){
  try{
    const s = await (await fetch('/api/status')).json();
    s.models.forEach(m => {
      const c = $('#chip-' + m.key); if (!c) return;
      c.classList.toggle('loaded', m.loaded); c.classList.toggle('missing', !m.installed);
      c.querySelector('.st').textContent = !s.ollama ? 'OFFLINE' : !m.installed ? 'AUSENTE' : m.loaded ? 'ATIVO NA RAM' : 'EM REPOUSO';
    });
  }catch(e){}
}
function markActive(key){ document.querySelectorAll('.chip').forEach(c => c.classList.toggle('active', c.id === 'chip-' + key)); }

/* ── módulo: eventos do servidor ────────────────────────── */
function onEvent(ev, m){
  const d = ev.data;
  switch (ev.event){
    case 'status': m.note.textContent = d; break;
    case 'route': markActive(d.key); m.tag.textContent = CFG.name + '  ·  ' + d.label + (d.tool ? '  +  ' + d.tool.toUpperCase() : d.web ? '  +  WEB' : ''); poll(); break;
    case 'think':
      if (!m.thinkEl){ const det = document.createElement('details'); det.innerHTML = '<summary>Raciocínio</summary><div></div>'; m.el.appendChild(det); m.thinkEl = det.querySelector('div'); }
      m.think += d; m.thinkEl.textContent = m.think; break;
    case 'memory': {
      const parts = [];
      if (d.saved.length) parts.push('guardei: ' + d.saved.join('; '));
      if (d.forgot.length) parts.push('esqueci: ' + d.forgot.join('; '));
      const n = document.createElement('div'); n.className = 'note'; n.textContent = 'Memória atualizada — ' + parts.join(' | ');
      m.el.appendChild(n); break; }
    case 'retract': m.full = ''; m.think = ''; m.bubble.textContent = ''; if (m.thinkEl){ m.thinkEl.parentElement.remove(); m.thinkEl = null; } break;
    case 'token': m.full += d; m.bubble.innerHTML = md(m.full); scroll(); break;
    case 'done':
      m.bubble.classList.remove('cursor'); markActive(null);
      m.note.textContent = d.seconds + 's' + (d.sources.length ? '  ·  ' + d.sources.length + ' fontes' : '') + (d.web_failed ? '  ·  busca na web falhou' : '') + (d.unloaded ? '  ·  RAM liberada' : '');
      if (d.sources.length){ const src = document.createElement('details'); src.innerHTML = '<summary>Fontes</summary>';
        d.sources.forEach(u => { const a = document.createElement('div'); a.textContent = u; src.appendChild(a); }); m.el.appendChild(src); }
      speak(m.full); poll(); break;
    case 'error':
      m.bubble.classList.remove('cursor'); m.bubble.textContent = d; m.bubble.style.borderColor = 'var(--err)'; m.note.textContent = ''; break;
  }
}

/* ── módulo: envio ──────────────────────────────────────── */
async function send(text){
  text = text.trim(); if (!text || busy) return;
  stopSpeech(); busy = true; stick = true; input.value = ''; setState('thinking');
  addMsg('user', text); const m = addMsg('jarvis'); ctrl = new AbortController();
  try{
    const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'},
                                        body: JSON.stringify({message: text}), signal: ctrl.signal});
    const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '';
    for (;;){
      const {done, value} = await rd.read(); if (done) break;
      buf += dec.decode(value, {stream:true}); let i;
      while ((i = buf.indexOf('\n')) >= 0){ const line = buf.slice(0, i); buf = buf.slice(i + 1); if (line.trim()) onEvent(JSON.parse(line), m); }
    }
  }catch(e){
    m.bubble.classList.remove('cursor');
    m.note.textContent = e.name === 'AbortError' ? 'Interrompido.' : 'Falha de comunicação: ' + e.message;
  }
  busy = false; markActive(null);
  if (!('speechSynthesis' in window) || !speechSynthesis.speaking) setState('idle');
}

/* ── eventos de interface ───────────────────────────────── */
$('#send').onclick = () => send(input.value);
input.onkeydown = e => { if (e.key === 'Enter') send(input.value); };
mic.onclick = toggleMic;
$('#stop').onclick = () => { stopSpeech(); if (ctrl) ctrl.abort(); setState('idle'); };
$('#voice').onclick = e => { ttsOn = !ttsOn; if (!ttsOn) stopSpeech(); e.target.textContent = 'Voz: ' + (ttsOn ? 'ligada' : 'desligada'); e.target.classList.toggle('off', !ttsOn); };
$('#reset').onclick = () => newConversation();
$('#unload').onclick = async () => { await fetch('/api/unload', {method:'POST'}); poll(); };
document.addEventListener('keydown', e => { if (e.key === 'Escape') $('#stop').click(); });

const dlg = $('#memdlg'), memtext = $('#memtext');
$('#mem').onclick = async () => {
  try{ const r = await (await fetch('/api/memory')).json(); memtext.value = r.text; $('#mempath').textContent = r.path; }
  catch(e){ memtext.value = 'Não foi possível carregar a memória.'; }
  dlg.showModal();
};
$('#memclose').onclick = () => dlg.close();
$('#memsave').onclick = async () => {
  await fetch('/api/memory', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text: memtext.value})});
  dlg.close();
};

/* Nova conversa: o servidor zera o contexto, lê o markdown de memória e devolve a saudação */
async function newConversation(){
  if (ctrl) ctrl.abort();
  stopSpeech(); log.innerHTML = ''; busy = true; stick = true;
  const m = addMsg('jarvis'); m.bubble.classList.remove('cursor'); m.bubble.textContent = 'Lendo memória...';
  try{
    const r = await (await fetch('/api/start', {method:'POST'})).json();
    m.bubble.textContent = r.greeting;
    m.note.textContent = r.facts ? 'memória carregada: ' + r.facts + ' fato(s)' : 'memória vazia';
  }catch(e){
    m.bubble.textContent = `Olá, ${CFG.title}. Todos os sistemas em operação. Como posso ajudar?`;
  }
  busy = false; setState('idle'); input.focus();
}
buildChips(); poll(); setInterval(poll, 4000); newConversation();
"""


def render_page():
    cfg = {"name": Config.ASSISTANT_NAME, "title": Config.USER_TITLE,
           "models": [{"key": k, "label": m["label"], "name": m["name"], "role": m["role"]}
                      for k, m in Config.MODELS.items()]}
    return (HTML.replace("__CSS__", CSS).replace("__JS__", JS)
            .replace("__CFG__", json.dumps(cfg, ensure_ascii=False))
            .replace("__NAME__", Config.ASSISTANT_NAME).replace("__TITLE__", Config.USER_TITLE))


# ════════════════════════════════════════════════════════════════════════════
# 9. SERVER
# ════════════════════════════════════════════════════════════════════════════
ASSISTANT = Assistant()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body, ctype="application/json; charset=utf-8", code=200):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _local(self):
        """Memória e controle de apps só para quem está no próprio computador."""
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def do_GET(self):
        if self.path == "/":
            self._send(render_page(), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self._send(json.dumps(ASSISTANT.models.status()))
        elif self.path == "/api/memory" and self._local():
            self._send(json.dumps({"text": ASSISTANT.memory.read(), "path": Config.MEMORY_FILE}))
        else:
            self._send("{}", code=404)

    def do_POST(self):
        size = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
        except ValueError:
            body = {}
        if self.path == "/api/chat":
            self._stream_chat((body.get("message") or "").strip())
        elif self.path == "/api/start":
            self._send(json.dumps(ASSISTANT.start_conversation(self._local()), ensure_ascii=False))
        elif self.path == "/api/reset":
            ASSISTANT.reset()
            self._send('{"ok":true}')
        elif self.path == "/api/unload":
            ASSISTANT.models.unload_all()
            self._send('{"ok":true}')
        elif self.path == "/api/memory" and self._local():
            text = str(body.get("text", ""))
            if len(text) > Config.MEMORY_MAX_CHARS * 2:
                return self._send('{"error":"texto grande demais"}', code=413)
            ASSISTANT.memory.write(text)
            self._send('{"ok":true}')
        else:
            self._send("{}", code=404)

    def _stream_chat(self, text):
        if not text:
            return self._send('{"error":"mensagem vazia"}', code=400)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(event, data):
            line = json.dumps({"event": event, "data": data}, ensure_ascii=False) + "\n"
            self.wfile.write(line.encode())
            self.wfile.flush()

        try:
            ASSISTANT.handle(text, emit, self._local())
        except (BrokenPipeError, ConnectionResetError):
            pass  # o navegador cancelou (botão Parar)
        except Exception as e:
            try:
                emit("error", f"Falha inesperada: {e}")
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description=Config.ASSISTANT_NAME)
    ap.add_argument("--host", default=Config.HOST)
    ap.add_argument("--port", type=int, default=Config.PORT)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    print(f"\n  {Config.ASSISTANT_NAME} — iniciando")
    st = ASSISTANT.models.status()
    if not st["ollama"]:
        print(f"  ! Ollama não respondeu em {Config.OLLAMA_URL}. Inicie com: ollama serve")
    for m in st["models"]:
        if st["ollama"] and not m["installed"]:
            print(f"  ! Modelo ausente: ollama pull {m['name']}")

    url = f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}"
    print(f"  Interface: {url}  (Ctrl+C para encerrar)\n")
    threading.Thread(target=ASSISTANT.tools.apps.catalog, daemon=True).start()   # lista os apps em segundo plano
    print(f"  Memória: {Config.MEMORY_FILE} ({len(ASSISTANT.memory.facts())} fatos)")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  Encerrando. Até logo.")


if __name__ == "__main__":
    main()
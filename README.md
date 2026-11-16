# J.A.R.V.I.S. — Assistente pessoal local

Assistente pessoal desenvolvido em **Python 3.14**, com modelos de linguagem executados localmente pelo [Ollama](https://ollama.com/). O projeto reúne conversa, pesquisa na internet, memória persistente e ferramentas para interagir com o computador em uma interface desktop inspirada no J.A.R.V.I.S.

> **Importante:** a geração das respostas acontece localmente no Ollama. Recursos como pesquisa na web, previsão do tempo e consulta ao YouTube dependem de conexão com a internet.

## Funcionalidades

- **Conversação local:** comunicação com o Ollama por sua API HTTP, sem depender de APIs comerciais de IA.
- **Roteamento inteligente:** um modelo gerente classifica o pedido e direciona a conversa para o modelo mais adequado.
- **Modelos sob demanda:** gerenciamento de carregamento e descarregamento dos modelos para reduzir o uso de RAM/VRAM.
- **Pesquisa na web:** consulta DuckDuckGo e Bing, leitura de páginas e extração de dados estruturados, sem chave de API.
- **YouTube:** pesquisa de vídeos, consulta de canais e identificação de publicações recentes, sem chave de API.
- **Previsão do tempo:** consulta de condições atuais e previsão para os próximos dias usando Open-Meteo.
- **Memória de longo prazo:** registra fatos relevantes em um arquivo Markdown local, que pode ser consultado e editado pela interface.
- **Automação do computador:** abertura de aplicativos, pastas, arquivos e sites; também oferece automação de mensagens em aplicativos configurados.
- **Visão computacional:** captura a tela e, quando habilitada, utiliza um modelo visual para localizar elementos e executar ações com mouse e teclado.
- **Interface desktop:** janela nativa via PyWebView, com modo normal e modo widget.
- **Voz:** síntese de fala e reconhecimento de voz por recursos do navegador/WebView, quando suportados pelo mecanismo instalado.

## Tecnologias

| Tecnologia | Finalidade |
|---|---|
| Python 3.14 | Aplicação principal |
| Ollama | Execução local dos modelos de IA |
| PyWebView | Janela desktop da interface |
| HTML, CSS e JavaScript | Interface gráfica |
| DuckDuckGo / Bing | Pesquisa na web |
| Open-Meteo | Dados meteorológicos |
| YouTube RSS e páginas públicas | Pesquisa e consulta de canais |
| MSS, Pillow e PyAutoGUI | Captura de tela e automação visual (opcional) |
| Playwright | Leitura de páginas renderizadas por JavaScript (opcional) |

## Requisitos

- **Python 3.14**.
- [Ollama instalado](https://ollama.com/download) e em execução.
- Conexão com a internet para baixar os modelos e utilizar os recursos de pesquisa, clima e YouTube.
- Um ambiente desktop com suporte ao mecanismo WebView exigido pelo PyWebView.
- Memória RAM e/ou VRAM compatível com os modelos escolhidos. O consumo depende do tamanho, da quantização e das opções de contexto de cada modelo.

O script não exige o pacote Python `ollama`: a comunicação com o Ollama é feita diretamente pela API HTTP. Também não há um `requirements.txt` obrigatório para o núcleo do projeto; as dependências opcionais são instaladas separadamente nas seções abaixo.

## Instalação

### 1. Baixe o projeto

Clone o repositório:

```bash
git clone https://github.com/FilipeGamer12/Jarvis_V4.git
cd <PASTA_DO_REPOSITORIO>
```

Ou baixe o ZIP do GitHub e extraia os arquivos. O arquivo principal deve ficar com o nome `jarvis.py`.

### 2. Confira o Python 3.14

No Windows:

```powershell
py -3.14 --version
```

No Linux ou macOS:

```bash
python3.14 --version
```

O comando deve retornar uma versão `Python 3.14.x`.

### 3. Crie um ambiente virtual

O ambiente virtual mantém as dependências do J.A.R.V.I.S. separadas de outros projetos Python.

**Windows — PowerShell:**

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

**Linux ou macOS:**

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Mantenha o ambiente virtual ativado nas próximas etapas e sempre que executar o projeto.

### 4. Instale a interface desktop

O PyWebView é necessário para abrir a janela do assistente.

**Windows:**

```bash
python -m pip install pywebview
```

No Windows, o mecanismo WebView2 do Microsoft Edge pode ser necessário. Consulte a [documentação de instalação do PyWebView](https://pywebview.idepy.com/en/guide/installation) caso a janela não abra.

**macOS:**

```bash
python -m pip install pywebview
```

Dependendo da instalação do Python, pode ser necessário instalar os componentes PyObjC indicados na documentação do PyWebView.

**Linux:**

Escolha um dos mecanismos suportados pelo PyWebView. Exemplo com Qt:

```bash
python -m pip install "pywebview[qt]"
```

Alternativamente, utilize o extra GTK:

```bash
python -m pip install "pywebview[gtk]"
```

Os pacotes de sistema do Qt, GTK e WebKit podem variar conforme a distribuição Linux. Consulte a [documentação oficial](https://pywebview.idepy.com/en/guide/installation).

### 5. Instale o Ollama

1. Baixe e instale o Ollama pelo site oficial: <https://ollama.com/download>.
2. Inicie o Ollama. Em instalações nas quais ele não inicia automaticamente, execute:

```bash
ollama serve
```

3. Em outro terminal, confirme que o comando está disponível:

```bash
ollama --version
```

Por padrão, o J.A.R.V.I.S. procura o serviço em `http://127.0.0.1:11434`.

### 6. Baixe os modelos padrão

O arquivo `jarvis.py` define estes modelos por padrão:

| Função | Modelo Ollama | Uso |
|---|---|---|
| Gerente | `lfm3:1.7b` | Conversa, classificação e roteamento |
| Conhecimento | `gemma4:12b` | Conhecimento geral e respostas com pesquisa web |
| Raciocínio | `deepseek-r1:14b` | Problemas complexos, lógica e programação |
| Visão | `qwen3-vl:8b-instruct` | Interpretação da tela e automação visual |

Baixe os modelos com os comandos:

```bash
ollama pull lfm3:1.7b
ollama pull gemma4:12b
ollama pull deepseek-r1:14b
ollama pull qwen3-vl:8b-instruct
```

Verifique se foram instalados:

```bash
ollama list
```

O modelo visual é utilizado apenas pela ferramenta de visão. Caso não pretenda utilizar esse recurso, desative `VISION_ENABLED` nas configurações do J.A.R.V.I.S.; assim, não será necessário baixar o modelo visual. **Use `qwen3-vl:8b-instruct`**, e não a variante `qwen3-vl:8b`.

Os modelos são carregados sob demanda. As opções padrão fazem o assistente liberar modelos pesados quando troca de função e após determinadas respostas, reduzindo a permanência simultânea de modelos na memória.

### 7. Inicie o J.A.R.V.I.S.

Com o Ollama em execução e o ambiente virtual ativado, entre na pasta do projeto e execute:

```bash
python jarvis.py
```

A janela desktop será aberta. Na primeira execução, o programa cria automaticamente os arquivos de configuração e memória, caso ainda não existam.

## Configuração

As configurações podem ser alteradas pelo painel de configurações da própria interface. As alterações são validadas e salvas em `jarvis_config.json`, localizado ao lado de `jarvis.py`.

### Configurações principais

| Opção | Padrão | Descrição |
|---|---|---|
| `HOST` | `127.0.0.1` | Endereço de rede em que o servidor local escuta |
| `PORT` | `8765` | Porta da interface e da API local |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Endereço da API do Ollama |
| `ASSISTANT_NAME` | `J.A.R.V.I.S.` | Nome exibido na interface |
| `USER_TITLE` | `senhor` | Forma de tratamento usada pelo assistente |
| `LANGUAGE` | `português do Brasil` | Idioma das respostas |
| `UI_MODE` | `normal` | Interface normal ou modo widget |
| `RESOURCE_SAVER_MODE` | `false` | Restringe o uso ao modelo gerente |
| `VOICE_ENABLED` | `true` | Ativa a leitura das respostas em voz alta |
| `AUTO_UNLOAD_IDLE` | `true` | Descarrega modelos após período sem atividade |
| `AUTO_UNLOAD_IDLE_MINUTES` | `5` | Minutos de inatividade antes de descarregar os modelos |

A alteração de `HOST` ou `PORT` exige reiniciar o programa. As demais opções são aplicadas pela interface quando possível.

### Modelos e roteamento

Na seção de modelos, é possível alterar os nomes dos modelos, suas funções, parâmetros de geração e tempo de permanência na memória. O roteador utiliza as seguintes rotas padrão:

- `chat`: modelo gerente (`manager`).
- `knowledge`: modelo de conhecimento (`knowledge`).
- `reasoning`: modelo de raciocínio (`reasoning`).

Os prefixos manuais disponíveis são:

| Prefixo | Rota forçada |
|---|---|
| `/chat` | Conversa com o modelo gerente |
| `/think` | Rota de conhecimento |
| `/hardwork` | Rota de raciocínio profundo |

Exemplos:

```text
/chat Olá, JARVIS.
/think Explique como funciona uma turbina eólica.
/hardwork Analise a complexidade deste algoritmo.
```

### Visão computacional

A visão computacional requer o modelo `qwen3-vl:8b-instruct` e as dependências opcionais abaixo. As principais opções são:

- `VISION_ENABLED`: ativa ou desativa a ferramenta.
- `VISION_CONTROL`: permite ou impede ações com mouse e teclado. Desative para limitar o recurso à observação da tela.
- `VISION_PLANNER`: define se o modelo gerente ou o modelo visual decide as ações.
- `VISION_MAX_STEPS`: limita o número de ações por solicitação.
- `VISION_MONITOR`: escolhe o monitor capturado.
- `VISION_DEBUG_LOG`: grava informações de depuração em `jarvis_vision.log`. Esse arquivo pode conter texto visto na tela; trate-o como dado privado.

Comandos de exemplo:

```text
/ver Descreva o que está visível na tela.
/pc Abra o navegador e pesquise por documentação do Python.
```

A automação visual pode clicar, digitar e pressionar teclas. Revise o resultado de cada ação e não deixe o computador executar operações sensíveis sem supervisão.

### Automação de aplicativos e mensagens

O assistente pode localizar aplicativos instalados, abrir e fechar programas, acessar pastas e arquivos, abrir sites e executar ações em aplicativos de mensagens cadastrados.

Os aplicativos de mensagens configurados por padrão são Discord e Slack. Para que o recurso funcione, o aplicativo correspondente precisa estar instalado e aberto ou poder ser iniciado pelo sistema.

**Atenção ao envio de mensagens:** o padrão do código é `SEND_MODE = "auto"`, que envia a mensagem após digitá-la. Recomenda-se alterar para uma destas opções antes de utilizar a automação:

- `confirm`: solicita confirmação antes do envio.
- `draft`: digita a mensagem, mas não pressiona Enter.
- `auto`: envia automaticamente.

Mantenha `ALLOW_EXECUTABLES = false` salvo se houver uma necessidade clara de permitir a abertura de executáveis ou scripts.

### Memória persistente

A memória de longo prazo fica em `jarvis_memory.md`, na mesma pasta do script por padrão. O assistente pode registrar fatos relevantes automaticamente e permite consultar ou editar o conteúdo pela interface.

Os arquivos gerados são locais. Faça cópias de segurança de `jarvis_config.json` e `jarvis_memory.md` se desejar preservar suas configurações e memória ao trocar de computador ou reinstalar o projeto.

## Dependências opcionais

### Visão computacional e controle do mouse/teclado

Instale:

```bash
python -m pip install mss pillow pyautogui
```

Esses pacotes só são necessários para utilizar a ferramenta que captura a tela e controla mouse e teclado. No Linux, podem existir requisitos adicionais de X11, Tk ou bibliotecas do sistema; no macOS, o sistema pode solicitar permissões de Acessibilidade e Captura de Tela.

### Leitura de páginas com JavaScript

A pesquisa web já consegue ler páginas HTML comuns. Para tentar ler páginas que dependem de renderização JavaScript, instale Playwright e o navegador Chromium:

```bash
python -m pip install playwright
python -m playwright install chromium
```

Esse recurso é opcional. Se não estiver instalado, o assistente continua utilizando os métodos de leitura HTTP disponíveis.

## Executar na rede local

Por padrão, o servidor escuta apenas no próprio computador (`127.0.0.1`). Para permitir que outros dispositivos da mesma rede acessem a interface pelo navegador, inicie com:

```bash
python jarvis.py --host 0.0.0.0 --port 8765
```

Em outro dispositivo, abra `http://IP_DO_COMPUTADOR:8765`, substituindo `IP_DO_COMPUTADOR` pelo endereço local da máquina que executa o J.A.R.V.I.S.

**Aviso de segurança:** o servidor HTTP não implementa autenticação de usuários nem HTTPS. Não encaminhe essa porta para a internet e não exponha o serviço diretamente em redes públicas. Algumas funções sensíveis, como memória, configurações e automação do computador, são restritas a requisições locais; o acesso remoto não equivale ao acesso completo da sessão desktop.

## Solução de problemas

### O J.A.R.V.I.S. informa que não consegue acessar o Ollama

1. Verifique se o Ollama está em execução.
2. Confirme o endereço configurado em `OLLAMA_URL`.
3. Teste a instalação com `ollama list`.
4. Confira se os nomes dos modelos em `jarvis_config.json` correspondem exatamente aos modelos baixados.

### Um modelo aparece como ausente

Execute o comando `ollama pull` correspondente ao modelo ausente. Exemplo:

```bash
ollama pull gemma4:12b
```

### A janela desktop não abre

Confirme a instalação do PyWebView e do mecanismo WebView da plataforma. No Windows, verifique o Microsoft Edge WebView2 Runtime. No Linux, confira se o extra Qt ou GTK e as bibliotecas de sistema correspondentes foram instalados.

### A visão computacional informa que faltam bibliotecas

Instale os pacotes opcionais:

```bash
python -m pip install mss pillow pyautogui
```

Verifique também se o modelo `qwen3-vl:8b-instruct` está instalado no Ollama e se `VISION_ENABLED` está ativado.

### O reconhecimento de voz não funciona

O reconhecimento utiliza a API de voz do navegador. O código recomenda Chrome ou Edge quando essa API não está disponível. Verifique também as permissões de microfone do sistema e do mecanismo WebView.

### A pesquisa web não encontra conteúdo de uma página

Alguns sites bloqueiam consultas automatizadas ou carregam o conteúdo inteiramente por JavaScript. Instale o Playwright conforme a seção de dependências opcionais ou tente novamente mais tarde.

## Estrutura dos arquivos

```text
projeto/
├── jarvis.py              # Aplicação principal
├── jarvis_config.json     # Configurações persistentes (gerado automaticamente)
├── jarvis_memory.md       # Memória de longo prazo (gerado automaticamente)
├── jarvis_vision.log      # Log da visão computacional (quando habilitado/gerado)
└── .venv/                 # Ambiente virtual Python (opcional, recomendado)
```

## Observações

- O arquivo principal concentra a aplicação, a interface HTML/CSS/JavaScript e o servidor HTTP.
- Os modelos são gerenciados pelo Ollama, não ficam armazenados dentro do repositório.
- Os recursos de pesquisa, clima e YouTube precisam de internet; as respostas dos modelos continuam sendo processadas pelo Ollama local.
- A compatibilidade do mecanismo de janela e das bibliotecas opcionais depende do sistema operacional e das dependências disponíveis para Python 3.14.

## Links úteis

- [Python 3.14](https://www.python.org/downloads/)
- [Ollama — Download](https://ollama.com/download)
- [Ollama — LFM3 1.7B](https://ollama.com/library/lfm3:1.7b)
- [Ollama — Gemma 4 12B](https://ollama.com/library/gemma4:12b)
- [Ollama — DeepSeek-R1 14B](https://ollama.com/library/deepseek-r1:14b)
- [Ollama — Qwen3-VL 8B Instruct](https://ollama.com/library/qwen3-vl:8b-instruct)
- [PyWebView — Instalação](https://pywebview.idepy.com/en/guide/installation)
- [Playwright para Python](https://playwright.dev/python/docs/intro)

---

Desenvolvido para execução local com Python e Ollama.

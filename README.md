# 🕹️ Arcade por Visão Computacional — Suíte de Jogos Interativos em Python

![Python](https://img.shields.io/badge/Python-3.9--3.12-blue.svg)
![Pygame](https://img.shields.io/badge/Pygame-2.5%2B-green.svg)
![OpenCV](https://img.shields.io/badge/OpenCV-4.11-red.svg)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.21-orange.svg)

Uma coleção de jogos arcade 2D feitos em **Python** com **Pygame**, em que a webcam vira o controle: o **MediaPipe Face Mesh** rastreia o rosto e o nariz em tempo real.

O arcade inteiro pode ser usado **sem teclado e sem mouse**: login, menu de jogos, partidas, menus de fim de jogo e até fechar o aplicativo são feitos com movimentos da cabeça e piscadas.

## ⬇️ Download

**[Baixe o instalador para Windows na página de Releases](https://github.com/VictorT-B/Bimbird/releases/latest)** (arquivo `FECArcade-Setup-<versão>.exe`), execute e pronto. Não precisa instalar Python nem nada mais. Requisitos: Windows 10/11 64 bits e uma webcam.

> O instalador não é assinado digitalmente. Se aparecer "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.

---

## 📋 Sumário

- [⬇️ Download](#️-download)
- [🙂 Como usar só com a cabeça](#-como-usar-só-com-a-cabeça)
- [🎮 Jogos incluídos](#-jogos-incluídos)
- [⚙️ Instalação e execução](#️-instalação-e-execução)
- [🎚️ Ajustes de sensibilidade](#️-ajustes-de-sensibilidade)
- [🧭 Como funciona o rastreamento](#-como-funciona-o-rastreamento)
- [💾 Dados dos jogadores](#-dados-dos-jogadores)
- [📁 Estrutura do repositório](#-estrutura-do-repositório)

---

## 🙂 Como usar só com a cabeça

A câmera calibra a posição neutra sozinha quando o rosto aparece. Se algo ficar descentralizado, basta sair da frente da câmera por 2 segundos e voltar.

### 1. Login (teclado digital)

| Ação | Movimento |
| --- | --- |
| Mover o cursor | Mover o **nariz** — o cursor segue a cabeça |
| Digitar a tecla sob o cursor | **Piscar devagar** (olhos fechados por ~0,25 s) |
| Alternativa à piscada | Deixar o cursor **parado 2 s** sobre a tecla |
| Entrar / criar usuário | Teclas **ENTRAR** (usuário existente) ou **CRIAR** (novo) |
| Fechar o arcade | Botão **X** no canto superior esquerdo |

Piscadas naturais (~0,1 s) são ignoradas, e o cursor congela enquanto o olho está fechado, para a letra não "escorregar".

### 2. Menu principal (hub)

| Ação | Movimento |
| --- | --- |
| Mudar de opção | Inclinar a cabeça para **cima** / **baixo** |
| Confirmar | Virar a cabeça para a **esquerda ou direita** e **segurar ~1 s** (uma barra amarela enche) |

Opções da coluna à esquerda: os 4 jogos, **Ranking**, **Trocar login** e **Sair**.

### 3. Menus dentro dos jogos

Todos os jogos usam as mesmas telas de **início** e **fim de jogo**, com os mesmos movimentos do hub:

- **Início:** `JOGAR` · `VOLTAR AO MENU`
- **Fim de jogo:** pontuação + `JOGAR DE NOVO` · `VOLTAR AO MENU`
- Antes de cada partida aparece uma contagem **"olhe para o centro da tela"** que calibra a câmera automaticamente.

### Teclado e mouse (opcional)

Continuam funcionando em todas as telas: setas/`W`/`S` navegam, `Enter`/`Espaço`/`←`/`→` confirmam, `ESC` volta (ou fecha, no login e no hub) e o mouse clica normalmente. No login, `F5` recalibra o cursor; no hub, `C` recalibra a cabeça.

---

## 🎮 Jogos incluídos

| Jogo | Controle | Multiplicador de pontos |
| --- | --- | --- |
| 🍉 Fruit Ninja | Nariz move a lâmina | x1.0 |
| 🐤 Nose Flappy | Altura do nariz | x1.5 |
| 🧺 Catch Fruit | Nariz para os lados | x2.0 |
| 🐦 Nosebird | Levantar a cabeça para pular | x3.0 |

Os pontos de cada partida, multiplicados, somam no total do jogador e no ranking.

### 🍉 Fruit Ninja no Cabeceio — [`Fruit Ninja/nose_fruit_ninja.py`](./Fruit%20Ninja/nose_fruit_ninja.py)

Corte melancias, laranjas, limões, morangos e uvas com o nariz e desvie das bombas. São 3 vidas; cada fruta que cai sem ser cortada custa uma.
- Barreira invisível (*"No-Fly Zone"*) que impede as frutas de cobrirem a prévia da webcam.
- Ondas progressivas de 1 a 5 frutas, partículas de suco e recorde salvo.
- Sem câmera, a lâmina segue o mouse.

### 🐤 Nose Flappy — [`nose_flappy/nose_flappy.py`](./nose_flappy/nose_flappy.py)

Flappy Bird controlado pela altura do rosto: levante a cabeça para subir e abaixe para descer.
- A velocidade dos canos e a frequência de spawn aumentam com a pontuação.
- Sem câmera, use as setas `↑`/`↓` ou `W`/`S`.

### 🧺 Catch Fruit — Pássaro Faminto — [`catch_fruit_game/game.py`](./catch_fruit_game/game.py)

Mova o pássaro para os lados com o nariz e pegue as frutas antes que caiam. São 3 vidas.
- Animações do pássaro reagindo, engolindo e mastigando.
- A dificuldade sobe a cada 12 pontos ou a cada 15 s.
- `H` mostra as hitboxes. **Precisa de webcam.**

### 🐦 Nosebird — [`nosebird/main.py`](./nosebird/main.py)

Corredor infinito: o personagem pula quando você levanta a cabeça.
- Dois personagens (**Bimbird** e **Ave Terror**), escolhidos no menu inicial; no fim de jogo há a opção `TROCAR PERSONAGEM`.
- Obstáculos (cactos, meteoros e pterossauros) e velocidade crescente.
- Sem câmera, use `Espaço` ou `↑`. `H` mostra as hitboxes e `F11` alterna a tela cheia.

---

## ⚙️ Instalação e execução

### Instalador Windows (usuário final)

Baixe `FECArcade-Setup-<versão>.exe` em [Releases](https://github.com/VictorT-B/Bimbird/releases/latest) e execute. O instalador:

- instala por usuário, sem pedir privilégios de administrador;
- cria um atalho no menu Iniciar (e, opcionalmente, na área de trabalho);
- já inclui Python, Pygame, OpenCV, MediaPipe e todos os assets;
- faz uma **instalação limpa**: o ranking começa vazio, sem usuários de outros computadores;
- guarda usuários, pontuações e recordes só neste computador, em `%LOCALAPPDATA%\FEC Arcade`, preservando-os em atualizações e desinstalações.

Requisitos: Windows 10/11 64 bits e uma webcam.

### Rodar pelo código-fonte

```bash
pip install -r requirements.txt
python launcher.py
```

Também dá para abrir um jogo sozinho, sem o hub (a pontuação não é salva sem um usuário logado):

```bash
cd "Fruit Ninja"
python nose_fruit_ninja.py
```

### Publicar uma versão nova (automático)

O GitHub gera e publica o instalador sozinho ([`.github/workflows/release.yml`](./.github/workflows/release.yml)). Basta criar uma tag com o número da versão:

```bash
git tag v1.2.0
git push origin v1.2.0
```

Em ~15 minutos a versão aparece em [Releases](https://github.com/VictorT-B/Bimbird/releases) com o instalador e o checksum SHA-256. Para só testar o build, sem publicar, use **Actions → Build e Release do instalador → Run workflow**; o instalador fica nos artefatos da execução.

### Gerar o instalador na sua máquina

Pré-requisitos: Python 3.12 64 bits, [Inno Setup 6](https://jrsoftware.org/isdl.php) e as dependências de [`requirements.txt`](./requirements.txt) e [`requirements-build.txt`](./requirements-build.txt).

No PowerShell, a partir da raiz do projeto:

```powershell
.\build-installer.ps1 -Python "C:\caminho\python.exe" -Version "1.2.0"
```

O script gera o ícone, grava a versão no executável, compila com PyInstaller ([`build/windows/FECArcade.spec`](./build/windows/FECArcade.spec)), roda o autoteste do pacote (`FECArcade.exe --self-test`), cria o instalador e grava o checksum SHA-256 em `dist\installer\`.

Para gerar só o aplicativo, sem o instalador:

```powershell
.\build-installer.ps1 -SkipInstaller
```

> Os jogos entram no pacote como arquivos de dados. Se um jogo passar a importar um novo módulo da raiz do projeto, adicione-o em `hiddenimports` no `.spec` (como já é feito com `game_menu`).

---

## 🎚️ Ajustes de sensibilidade

Todos os valores ficam no topo dos arquivos indicados.

| O que ajustar | Arquivo | Constante |
| --- | --- | --- |
| Inclinação para cima/baixo no hub | [`head_menu.py`](./head_menu.py) | `PITCH_THRESHOLD` |
| Virada para o lado no hub | [`head_menu.py`](./head_menu.py) | `YAW_THRESHOLD` |
| Tempo segurando para confirmar | [`head_menu.py`](./head_menu.py) / [`game_menu.py`](./game_menu.py) | `SELECT_HOLD_S` |
| Sensibilidade do cursor do login | [`head_menu.py`](./head_menu.py) | `CURSOR_RANGE_X`, `CURSOR_RANGE_Y` (menor = mais sensível) |
| Facilidade de detectar a piscada | [`head_menu.py`](./head_menu.py) | `BLINK_CLOSE_RATIO` (maior = detecta mais fácil) |
| Duração mínima da piscada | [`head_menu.py`](./head_menu.py) | `BLINK_MIN_S` |
| Seleção por permanência no login | [`launcher.py`](./launcher.py) | `DWELL_SELECT_S` (`0` desativa) |
| Movimentos nos menus dos jogos | [`game_menu.py`](./game_menu.py) | `NAV_THRESHOLD`, `SELECT_THRESHOLD` |
| Pausa antes do menu de fim de jogo | [`game_menu.py`](./game_menu.py) | `DEATH_DELAY_MS` |

---

## 🧭 Como funciona o rastreamento

- **Thread dedicada:** a captura da webcam e o MediaPipe rodam em uma thread separada, e o Pygame segue a 60 FPS.
- **Hub e login ([`head_menu.py`](./head_menu.py)):** a direção da cabeça é medida por **razões entre pontos do rosto** (nariz em relação a testa/queixo e às bochechas). Assim o controle depende só da rotação da cabeça, não da distância nem da posição na câmera. Gatilhos com **histerese** evitam disparos repetidos: a cabeça precisa voltar perto do neutro para disparar de novo.
- **Cursor do login:** posição do nariz relativa à largura do rosto, suavizada com um **filtro One Euro** (quase sem tremor parado, sem atraso em movimento).
- **Piscada:** calculada pelo **EAR** (*Eye Aspect Ratio*, abertura dos olhos) comparado com a abertura normal de cada pessoa, que o sistema aprende sozinho.
- **Menus dos jogos ([`game_menu.py`](./game_menu.py)):** usam a posição do nariz que cada jogo já rastreia, com a mesma lógica de gatilhos do hub.
- **Uma câmera, um dono por vez:** o launcher libera a webcam antes de abrir um jogo (cada jogo roda em um processo próprio) e a retoma quando o jogo fecha.

---

## 💾 Dados dos jogadores

Os dados são **locais de cada computador**:

- Banco SQLite em `%LOCALAPPDATA%\FEC Arcade\arcade.db` (ou na pasta definida pela variável de ambiente `FEC_ARCADE_DATA_DIR`), com usuários, histórico de partidas e ranking. O recorde do Fruit Ninja fica na mesma pasta.
- Uma instalação nova sempre começa com o **banco vazio**. Nenhum banco é empacotado no instalador nem copiado automaticamente.
- O usuário **`admin`** pode apagar jogadores pelo ranking do hub (clicando no `X` ao lado do nome).

### Transferir o ranking para outro computador (só se for a intenção)

```powershell
# No computador de origem: gera um arquivo com o ranking
FECArcade.exe --export-db "D:\ranking.db"

# No computador de destino: substitui o ranking local pelo do arquivo
FECArcade.exe --import-db "D:\ranking.db"
```

Pelo código-fonte, use `python app.py` no lugar de `FECArcade.exe`. A importação valida o arquivo antes e guarda o banco anterior como `arcade.db.bak-<data>` na mesma pasta, então dá para desfazer.

---

## 📁 Estrutura do repositório

```text
fec 2026/
├── app.py                        # Ponto de entrada (executável): launcher, jogos, --self-test e --export-db/--import-db
├── launcher.py                   # Login com teclado digital + hub de jogos
├── head_menu.py                  # Controle pela cabeça: gestos do hub, cursor do nariz e piscada
├── game_menu.py                  # Menus padronizados de início/fim de jogo (usados pelos 4 jogos)
├── database.py                   # Usuários, pontuações e ranking (SQLite local)
├── imagem_geral.jpeg             # Fundo do launcher
├── logo.png                      # Logo do projeto
├── PressStart2P.ttf              # Fonte pixel art da interface
├── Fruit Ninja/
│   ├── nose_fruit_ninja.py       # Fruit Ninja no Cabeceio
│   └── sprites/                  # Frutas, bomba, sucos, coração e fundo
├── nose_flappy/
│   ├── nose_flappy.py            # Nose Flappy
│   └── sprites/                  # Pássaro, canos, partículas e fundo
├── catch_fruit_game/
│   ├── game.py                   # Catch Fruit (Pássaro Faminto)
│   └── assets/                   # Sprites do pássaro, frutas e fundo
├── nosebird/
│   ├── main.py                   # Loop principal do Nosebird
│   ├── entities.py               # Jogador, obstáculos e partículas
│   ├── settings.py               # Dimensões, física e paleta de cores
│   ├── tracker.py                # Rastreamento do nariz (detecção de pulo)
│   └── sprites/                  # Personagens, obstáculos e fundo
├── .github/workflows/release.yml # Gera e publica o instalador ao criar uma tag v*
├── build/windows/                # .spec do PyInstaller, script do Inno Setup, ícone e versão
├── build-installer.ps1           # Pipeline de build do instalador
├── .gitignore                    # Impede versionar bancos de dados, caches e builds
├── requirements.txt              # Dependências do jogo
└── requirements-build.txt        # Dependências de build (PyInstaller etc.)
```

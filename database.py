"""Banco SQLite do arcade: usuários, histórico de partidas e ranking.

Os dados são sempre locais ao computador: ficam em
%LOCALAPPDATA%\\FEC Arcade\\arcade.db (ou em FEC_ARCADE_DATA_DIR, se definido).
Uma instalação nova começa com o banco vazio. Levar o ranking para outra máquina
só acontece de forma explícita, com export_database() / import_database()
(no executável: --export-db / --import-db).
"""

import os
import shutil
import sqlite3
import time

APP_DATA_FOLDER = "FEC Arcade"


def get_data_dir():
    override = os.environ.get("FEC_ARCADE_DATA_DIR")
    if override:
        return os.path.abspath(override)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return os.path.join(local_app_data, APP_DATA_FOLDER)
    return os.path.join(os.path.expanduser("~"), ".fec_arcade")


DATA_DIR = get_data_dir()
DB_PATH = os.path.join(DATA_DIR, "arcade.db")

MULTIPLIERS = {
    "Fruit Ninja": 1.0,
    "Nose Flappy": 1.5,
    "Catch Fruit Game": 2.0,
    "Nosebird": 3.0,
}


def get_connection():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def get_user(nickname):
    nickname = nickname.strip()
    if not nickname:
        return None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nickname, total_points FROM users "
        "WHERE nickname = ? COLLATE NOCASE",
        (nickname,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None
    return {"id": row[0], "nickname": row[1], "total_points": row[2]}


def create_user(nickname):
    nickname = nickname.strip()
    if not nickname:
        raise ValueError("O nome do usuário não pode ficar vazio.")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM users WHERE nickname = ? COLLATE NOCASE", (nickname,)
    )
    if cursor.fetchone() is not None:
        conn.close()
        return None

    cursor.execute(
        "INSERT INTO users (nickname, total_points) VALUES (?, ?)",
        (nickname, 0.0),
    )
    conn.commit()
    user = {"id": cursor.lastrowid, "nickname": nickname, "total_points": 0.0}
    conn.close()
    return user


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Tabela de usuários
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT UNIQUE NOT NULL,
            total_points REAL DEFAULT 0.0
        )
    """)

    # Tabela de pontuações (histórico de partidas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            game_name TEXT NOT NULL,
            base_score REAL NOT NULL,
            multiplier REAL NOT NULL,
            points_earned REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    conn.commit()
    conn.close()


def get_or_create_user(nickname):
    """
    Retorna o dicionário do usuário. Se não existir, cria um novo com 0 pontos.
    """
    nickname = nickname.strip()
    user = get_user(nickname)
    if user is not None:
        return user

    created_user = create_user(nickname)
    if created_user is not None:
        return created_user
    return get_user(nickname)


def save_score(nickname, game_name, base_score):
    """
    Salva a pontuação da partida e atualiza o total do usuário.
    O multiplicador é aplicado automaticamente dependendo do jogo.
    """
    user = get_or_create_user(nickname)
    multiplier = MULTIPLIERS.get(game_name, 1.0)
    points_earned = float(base_score) * multiplier

    conn = get_connection()
    cursor = conn.cursor()

    # Salva no histórico de scores
    cursor.execute(
        """
        INSERT INTO scores (user_id, game_name, base_score, multiplier, points_earned)
        VALUES (?, ?, ?, ?, ?)
    """,
        (user["id"], game_name, float(base_score), multiplier, points_earned),
    )

    # Atualiza a pontuação total do usuário
    cursor.execute(
        """
        UPDATE users SET total_points = total_points + ? WHERE id = ?
    """,
        (points_earned, user["id"]),
    )

    conn.commit()
    conn.close()

    return points_earned


def get_leaderboard(limit=10):
    """
    Retorna o ranking de usuários, do maior para o menor (Torneio).
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT nickname, total_points FROM users ORDER BY total_points DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()

    conn.close()
    return rows


def delete_user(nickname):
    nickname = nickname.strip()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE nickname = ? COLLATE NOCASE", (nickname,))
    row = cursor.fetchone()
    if row:
        user_id = row[0]
        cursor.execute("DELETE FROM scores WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Transferência explícita de dados entre computadores
# ---------------------------------------------------------------------------
def export_database(destination):
    """Copia o banco local para `destination` (uma cópia consistente, mesmo
    com o arcade aberto). Retorna o caminho gerado."""
    destination = os.path.abspath(destination)
    if os.path.isdir(destination):
        destination = os.path.join(destination, "arcade.db")
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    source = get_connection()
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


def import_database(source_path):
    """Substitui o banco local pelo arquivo `source_path`.
    O banco atual é preservado como arcade.db.bak-<data> na pasta de dados.
    Retorna o caminho do backup (ou None se não havia banco)."""
    source_path = os.path.abspath(source_path)
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {source_path}")
    if os.path.abspath(DB_PATH) == source_path:
        raise ValueError("O arquivo informado já é o banco local.")

    # Valida que é um banco do arcade antes de mexer em qualquer coisa
    conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"O arquivo não é um banco SQLite válido: {exc}") from exc
    finally:
        conn.close()
    if not {"users", "scores"} <= tables:
        raise ValueError("O arquivo não é um banco do FEC Arcade (faltam tabelas).")

    os.makedirs(DATA_DIR, exist_ok=True)
    backup_path = None
    if os.path.exists(DB_PATH):
        backup_path = f"{DB_PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(DB_PATH, backup_path)
    temporary_path = f"{DB_PATH}.importing"
    shutil.copy2(source_path, temporary_path)
    os.replace(temporary_path, DB_PATH)
    return backup_path


# Inicializa as tabelas ao ser importado pela primeira vez
# (num computador novo, cria um banco vazio)
init_db()

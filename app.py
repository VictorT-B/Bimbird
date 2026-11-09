"""Ponto de entrada do FEC Arcade (também usado pelo executável).

    FECArcade.exe                      abre o arcade
    FECArcade.exe --game <id> <nick>   roda um jogo (usado pelo launcher)
    FECArcade.exe --self-test          verifica o pacote (usado no build)
    FECArcade.exe --export-db <arq>    exporta o ranking local para um arquivo
    FECArcade.exe --import-db <arq>    substitui o ranking local por um arquivo
"""

import os
import runpy
import sys

GAME_SCRIPTS = {
    "fruit-ninja": os.path.join("Fruit Ninja", "nose_fruit_ninja.py"),
    "nose-flappy": os.path.join("nose_flappy", "nose_flappy.py"),
    "catch-fruit": os.path.join("catch_fruit_game", "game.py"),
    "nosebird": os.path.join("nosebird", "main.py"),
}

REQUIRED_ASSETS = [
    "imagem_geral.jpeg",
    "logo.png",
    "PressStart2P.ttf",
    os.path.join("Fruit Ninja", "sprites", "fruitfundo.png"),
    os.path.join("nose_flappy", "sprites", "background_nuclear.png"),
    os.path.join("catch_fruit_game", "assets", "bg", "background.png"),
    os.path.join("nosebird", "sprites", "background_dino.png"),
]


def resource_path(*parts):
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, *parts)


def run_game(game_id, nickname):
    relative_script = GAME_SCRIPTS.get(game_id)
    if relative_script is None:
        raise ValueError(f"Jogo desconhecido: {game_id}")

    script_path = resource_path(relative_script)
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Arquivo do jogo não encontrado: {script_path}")

    game_dir = os.path.dirname(script_path)
    previous_cwd = os.getcwd()
    previous_argv = sys.argv[:]
    sys.path.insert(0, game_dir)
    try:
        os.chdir(game_dir)
        sys.argv = [script_path, nickname]
        runpy.run_path(script_path, run_name="__main__")
    finally:
        os.chdir(previous_cwd)
        sys.argv = previous_argv
        if sys.path and sys.path[0] == game_dir:
            sys.path.pop(0)


def self_test():
    import mediapipe as mp
    import cv2
    import pygame

    import game_menu  # noqa: F401  (menus dos jogos)
    import head_menu  # noqa: F401  (controle do launcher pela cabeça)

    if not hasattr(mp, "solutions") or not hasattr(mp.solutions, "face_mesh"):
        raise RuntimeError("MediaPipe FaceMesh não está disponível.")
    if not cv2.__version__ or not pygame.version.ver:
        raise RuntimeError("OpenCV ou Pygame não foi carregado corretamente.")

    face_mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=False,
    )
    face_mesh.close()

    required_files = list(GAME_SCRIPTS.values()) + REQUIRED_ASSETS
    missing = [path for path in required_files if not os.path.isfile(resource_path(path))]
    if missing:
        raise FileNotFoundError(f"Arquivos ausentes no pacote: {', '.join(missing)}")


def notify(message, error=False):
    """Mostra o resultado de um comando (o executável não tem console)."""
    print(message, file=sys.stderr if error else sys.stdout)
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        import ctypes

        icon = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, message, "FEC Arcade", icon)


def transfer_data(command, path):
    """--export-db / --import-db: levar o ranking para outro computador.
    Só acontece quando pedido explicitamente; a instalação padrão é limpa."""
    import database

    try:
        if command == "--export-db":
            out = database.export_database(path)
            notify(f"Ranking exportado para:\n{out}")
        else:
            backup = database.import_database(path)
            msg = f"Ranking importado de:\n{os.path.abspath(path)}"
            if backup:
                msg += f"\n\nO banco anterior foi guardado em:\n{backup}"
            notify(msg)
    except Exception as exc:
        notify(f"Não foi possível concluir: {exc}", error=True)
        sys.exit(1)


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
        return

    if len(sys.argv) == 3 and sys.argv[1] in ("--export-db", "--import-db"):
        transfer_data(sys.argv[1], sys.argv[2])
        return

    if len(sys.argv) >= 4 and sys.argv[1] == "--game":
        run_game(sys.argv[2], sys.argv[3])
        return

    import launcher

    launcher.main()


if __name__ == "__main__":
    main()

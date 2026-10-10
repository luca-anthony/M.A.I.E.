import argparse

from maie import config


def parse():
    parser = argparse.ArgumentParser(prog="main.py")
    parser.add_argument("--mode", choices=["online", "pc", "local"])
    parser.add_argument("--profile", choices=["pc", "pi"])
    parser.add_argument("--config")
    parser.add_argument("--text-only", action="store_true")
    parser.add_argument("--no-tts", action="store_true")
    parser.add_argument("--list-devices", action="store_true")
    return parser.parse_args()


def list_devices():
    try:
        import sounddevice as sd

        print(sd.query_devices())
    except Exception as exc:
        print(f"audio devices unavailable: {exc}")
    try:
        import pygame

        pygame.display.init()
        print("displays:", pygame.display.get_desktop_sizes())
    except Exception as exc:
        print(f"displays unavailable: {exc}")


def main():
    args = parse()
    if args.list_devices:
        list_devices()
        return
    cfg = config.load(args.config, args.profile, args.mode)
    from maie.app import App

    app = App(cfg, text_only=args.text_only, no_tts=args.no_tts)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()

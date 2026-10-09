# M.A.I.E.

Multi-purpose AI for Interactive Environments

Runs in three modes, switchable at any time:

| Mode   | Where the model runs                          | If it is unreachable |
|--------|-----------------------------------------------|----------------------|
| online | Ollama cloud model                            | falls back to local  |
| pc     | Ollama on your PC, reached over LAN/Tailscale | falls back to local  |
| local  | Small model on the Raspberry Pi itself        | none                 |

Quick start on the PC:

    python -m venv .venv
    . .venv/bin/activate
    pip install -r requirements-pc.txt
    python main.py --mode online

Type /help inside the program for commands. Full instructions are in SETUP.md.

#!/usr/bin/env python3
"""Conveniencia: executa o pipeline HF Brasil.

Uso:
    python run.py --dry-run -v

Equivalente a:
    hfbrasil-preco --dry-run -v
"""

from hfbrasil_preco.cli import main

if __name__ == "__main__":
    main()

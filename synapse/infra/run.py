# synapse/infra/run.py
"""
Infra runner para evitar los warnings típicos de runpy cuando
ya importaste módulos y luego ejecutas `python -m synapse.infra.doctor`.

Uso:
  python -m synapse.infra.run doctor
"""

from __future__ import annotations

import sys


def _run_doctor(argv: list[str]) -> int:
    # Import lazy: aquí sí cargamos doctor, porque lo estamos ejecutando.
    from synapse.infra import doctor as _doctor  # noqa: WPS433

    # doctor._cli() debería existir; si no, caemos a main()
    if hasattr(_doctor, "_cli"):
        return int(_doctor._cli(argv))
    if hasattr(_doctor, "main"):
        return int(_doctor.main(argv))
    raise SystemExit("doctor module no expone _cli() ni main()")


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    cmd = (argv[0] if argv else "").strip().lower()

    if cmd in {"doctor", "doc"}:
        return _run_doctor(argv[1:])

    print("Uso: python -m synapse.infra.run doctor")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

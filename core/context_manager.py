"""
Mantiene el contexto de la sesión de escritorio: qué app está activa,
su título y la última acción ejecutada.

Permite a SOFIA resolver referencias implícitas como "ciérrala" o
"minimízala" sin que el usuario repita el nombre de la app.
"""

from datetime import datetime


class ContextManager:
    def __init__(self):
        self._ctx: dict = {
            "app": None,
            "titulo": None,
            "ultima_accion": None,
            "contenido_resumen": "",
            "timestamp": None,
        }

    def actualizar(self, app: str, titulo: str, accion: str = None, contenido: str = ""):
        self._ctx = {
            "app": app.lower().strip() if app else None,
            "titulo": titulo.strip() if titulo else None,
            "ultima_accion": accion,
            "contenido_resumen": contenido or "",
            "timestamp": datetime.now().isoformat(),
        }

    def app_activa(self) -> str | None:
        return self._ctx.get("app")

    def titulo_activo(self) -> str | None:
        return self._ctx.get("titulo")

    def ultima_accion(self) -> str | None:
        return self._ctx.get("ultima_accion")

    def snapshot(self) -> dict:
        return dict(self._ctx)

    def contenido_resumen(self) -> str:
        return self._ctx.get("contenido_resumen", "")

    def tiene_contexto(self) -> bool:
        return self._ctx.get("app") is not None


contexto = ContextManager()

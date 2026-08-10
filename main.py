import flet as ft

from app.page import build_page


def main(page: ft.Page):
    """Flet entrypoint that delegates dashboard construction and runtime loops."""
    build_page(page)


ft.app(target=main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=8550)

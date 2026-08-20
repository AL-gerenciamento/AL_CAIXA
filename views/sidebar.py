"""
views/sidebar.py
Menu lateral de navegação entre as telas do sistema.
"""
import customtkinter as ctk

from models import Permissao

ITENS_MENU = [
    ("Dashboard", "🏠"),
    ("Caixa / Venda", "🧾"),
    ("Produtos", "📦"),
    ("Estoque e Produção", "🏭"),
    ("Receitas", "💵"),
    ("Despesas", "💸"),
    ("Categorias", "🏷️"),
    ("Metas Financeiras", "🎯"),
    ("Relatórios", "📊"),
    ("Central de Ajuda", "❓"),
    ("Configurações", "⚙️"),
]

# Itens visíveis apenas para usuários com permissão de Administrador
ITENS_MENU_ADMIN = [
    ("Administração", "👥"),
]


class Sidebar(ctk.CTkFrame):
    """Barra lateral fixa com os itens de navegação principais."""

    def __init__(self, master, ao_selecionar, usuario):
        super().__init__(master, width=220, corner_radius=0)
        self.ao_selecionar = ao_selecionar
        self.usuario = usuario
        self.botoes: dict[str, ctk.CTkButton] = {}
        self.grid_propagate(False)
        self._construir_layout()

    def _construir_layout(self) -> None:
        ctk.CTkLabel(
            self, text="💰 Financeiro", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(padx=20, pady=(25, 5), anchor="w")
        ctk.CTkLabel(
            self, text=f"Olá, {self.usuario.nome.split()[0]}", text_color="gray"
        ).pack(padx=20, pady=(0, 20), anchor="w")

        itens = list(ITENS_MENU)
        if self.usuario.permissao == Permissao.ADMIN:
            # Insere os itens exclusivos de admin logo antes de "Configurações"
            itens = itens[:-1] + ITENS_MENU_ADMIN + itens[-1:]

        for nome, icone in itens:
            botao = ctk.CTkButton(
                self, text=f"{icone}  {nome}", anchor="w", height=40,
                fg_color="transparent", hover_color=("gray80", "gray25"),
                command=lambda n=nome: self._selecionar(n),
            )
            botao.pack(padx=12, pady=3, fill="x")
            self.botoes[nome] = botao

        self._selecionar("Dashboard")

    def _selecionar(self, nome: str) -> None:
        """Destaca visualmente o item ativo e propaga a seleção."""
        for chave, botao in self.botoes.items():
            botao.configure(fg_color="#3B8ED0" if chave == nome else "transparent")
        self.ao_selecionar(nome)

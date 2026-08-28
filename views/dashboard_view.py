"""
views/dashboard_view.py
Tela inicial: nome da empresa, área de destaque (logo) à esquerda e
grade de acesso rápido às funções mais usadas à direita.
O resumo financeiro (cards, gráficos, últimas movimentações) fica na
tela de Relatórios, aba "Resumo".
"""
import os

import customtkinter as ctk
from PIL import Image, ImageOps

from models import Permissao


class DashboardView(ctk.CTkFrame):
    """Tela inicial: nome da empresa, destaque à esquerda e menu de acesso rápido à direita."""

    def __init__(self, master, ao_navegar=None, usuario=None):
        super().__init__(master, fg_color="transparent")
        self.ao_navegar = ao_navegar
        self.usuario = usuario
        self._construir_layout()

    def _construir_layout(self) -> None:
        empresa = getattr(self.usuario, "empresa", None) if self.usuario else None
        nome_empresa = "AL Caixa"
        if empresa is not None:
            nome_empresa = empresa.nome_fantasia or empresa.nome

        ctk.CTkLabel(
            self, text=nome_empresa, font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(anchor="w", padx=30, pady=(25, 15))

        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        corpo.grid_columnconfigure(0, weight=1)
        corpo.grid_columnconfigure(1, weight=1)
        corpo.grid_rowconfigure(0, weight=1)

        self._construir_destaque(corpo, empresa)
        self._construir_menu_inicial(corpo)

    # --- Coluna esquerda: foto do mercado (logo/foto cadastrada em Configurações) ---
    def _construir_destaque(self, master, empresa) -> None:
        self._caminho_foto = getattr(empresa, "logo_path", None) if empresa else None
        self._imagem_pil = None
        if self._caminho_foto and os.path.isfile(self._caminho_foto):
            try:
                self._imagem_pil = Image.open(self._caminho_foto)
            except Exception:
                self._imagem_pil = None

        caixa = ctk.CTkFrame(
            master, corner_radius=18, fg_color=("gray95", "gray17"),
            border_width=1, border_color=("gray80", "gray30"),
        )
        caixa.grid(row=0, column=0, sticky="nsew", padx=(0, 15))

        if self._imagem_pil is not None:
            self.label_foto = ctk.CTkLabel(caixa, text="")
            self.label_foto.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._ultimo_tamanho_foto = (0, 0)
            caixa.bind("<Configure>", self._redimensionar_foto)
        else:
            conteudo = ctk.CTkFrame(caixa, fg_color="transparent")
            conteudo.place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(conteudo, text="🏪", font=ctk.CTkFont(size=90)).pack()
            ctk.CTkLabel(
                conteudo, text="Nenhuma foto do mercado cadastrada",
                font=ctk.CTkFont(size=13), text_color=("gray35", "gray70"),
            ).pack(pady=(10, 2))
            ctk.CTkLabel(
                conteudo, text="Configurações → Selecionar imagem",
                font=ctk.CTkFont(size=11), text_color=("gray50", "gray55"),
            ).pack()

    def _redimensionar_foto(self, evento) -> None:
        largura, altura = evento.width, evento.height
        if largura < 10 or altura < 10:
            return
        if (largura, altura) == getattr(self, "_ultimo_tamanho_foto", None):
            return
        self._ultimo_tamanho_foto = (largura, altura)
        try:
            recortada = ImageOps.fit(self._imagem_pil, (largura, altura), method=Image.LANCZOS)
        except Exception:
            return
        foto = ctk.CTkImage(light_image=recortada, dark_image=recortada, size=(largura, altura))
        self.label_foto.configure(image=foto)
        self.label_foto.image = foto

    # --- Coluna direita: menu de acesso rápido (grade 5 colunas, estilo PDV) ---
    def _construir_menu_inicial(self, master) -> None:
        area = ctk.CTkScrollableFrame(master, fg_color="transparent")
        area.grid(row=0, column=1, sticky="nsew")

        if self.ao_navegar is None:
            return

        # (destino, emoji, cor, subtitulo, atalho)
        itens = [
            ("Caixa / Venda", "🧾", "#2ECC71", "Nova venda", "F3"),
            ("Histórico de Vendas", "📜", "#1ABC9C", "Vendas em aberto e concluídas", None),
            ("Produtos", "📦", "#3498DB", "Cadastro e preços", None),
            ("Estoque e Produção", "🏭", "#16A085", "Controle de estoque", None),
            ("Receitas", "💵", "#27AE60", "Lançar receita", "Ctrl+R"),
            ("Despesas", "💸", "#E67E22", "Lançar despesa", "Ctrl+E"),
            ("Categorias", "🏷️", "#8E44AD", "Organizar categorias", None),
            ("Metas Financeiras", "🎯", "#9B59B6", "Acompanhar metas", "Ctrl+M"),
            ("Relatórios", "📊", "#2980B9", "Resumo e exportação", None),
            ("Configurações", "⚙️", "#7F8C8D", "Ajustes do sistema", None),
            ("Central de Ajuda", "❓", "#34495E", "Dúvidas e suporte", None),
        ]
        if self.usuario is not None and self.usuario.permissao == Permissao.ADMIN:
            itens.append(("Administração", "👥", "#C0392B", "Usuários e contas", None))

        # Só mostra o que o usuário tem permissão de acessar.
        if self.usuario is not None:
            itens = [item for item in itens if self.usuario.tem_permissao(item[0])]

        itens.append(("__sair__", "🚪", "#95A5A6", "Sair do sistema", None))

        colunas = 5
        linhas = (len(itens) + colunas - 1) // colunas
        for c in range(colunas):
            area.grid_columnconfigure(c, weight=1, uniform="cartao_col")
        for r in range(linhas):
            area.grid_rowconfigure(r, weight=1, uniform="cartao_row")

        for i, (destino, emoji, cor, subtitulo, atalho) in enumerate(itens):
            titulo = "Sair do Sistema" if destino == "__sair__" else destino
            self._botao_menu(area, i, titulo, emoji, cor, subtitulo, destino, atalho)

        if len(itens) == 1:
            ctk.CTkLabel(
                area, text="Nenhum módulo liberado para este usuário. Solicite acesso ao administrador.",
                text_color="orange",
            ).pack(anchor="w", pady=20)

    def _botao_menu(self, master, coluna: int, titulo: str, emoji: str, cor: str,
                     subtitulo: str, destino: str, atalho: str | None = None) -> None:
        item = ctk.CTkFrame(
            master, corner_radius=14, fg_color=("gray92", "gray20"),
            border_width=1, border_color=("gray80", "gray30"),
        )
        item.grid(row=coluna // 5, column=coluna % 5, padx=6, pady=6, sticky="nsew")

        conteudo = ctk.CTkFrame(item, fg_color="transparent")
        conteudo.pack(padx=6, pady=8, expand=True)

        ctk.CTkButton(
            conteudo, text=emoji, width=42, height=42, corner_radius=10,
            fg_color=cor, hover_color=cor, font=ctk.CTkFont(size=16),
            command=lambda d=destino: self.ao_navegar(d),
        ).pack()

        ctk.CTkLabel(
            conteudo, text=titulo, font=ctk.CTkFont(size=10, weight="bold"),
            wraplength=80, justify="center",
        ).pack(pady=(5, 0))
        if atalho:
            ctk.CTkLabel(
                conteudo, text=atalho, font=ctk.CTkFont(size=7, weight="bold"),
                fg_color=cor, text_color="white", corner_radius=5, padx=4,
            ).pack(pady=(2, 0))
        ctk.CTkLabel(
            conteudo, text=subtitulo, font=ctk.CTkFont(size=7), text_color="gray",
            wraplength=80, justify="center",
        ).pack(pady=(2, 0))

"""
views/receitas_view.py
Tela de gestão de receitas: listagem, filtros, criação, edição e exclusão.
"""
from datetime import date, datetime

import customtkinter as ctk
from tkinter import messagebox

from controllers.receita_controller import ReceitaController
from controllers.categoria_controller import CategoriaController
from controllers.config_controller import ConfigController
from utils.validators import ValidationError


class ReceitasView(ctk.CTkFrame):
    """CRUD completo de receitas com pesquisa e filtros."""

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self.moeda = ConfigController.obter("moeda")
        self.categorias = CategoriaController.listar(tipo="receita")
        self._construir_layout()
        self._atualizar_lista()

    def _construir_layout(self) -> None:
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=30, pady=(25, 10))

        ctk.CTkLabel(
            topo, text="Receitas", font=ctk.CTkFont(size=26, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(
            topo, text="+ Nova Receita", command=self._abrir_formulario
        ).pack(side="right")

        # --- Filtros ---
        filtros = ctk.CTkFrame(self, fg_color="transparent")
        filtros.pack(fill="x", padx=30, pady=(0, 10))

        self.entry_pesquisa = ctk.CTkEntry(filtros, placeholder_text="Pesquisar por descrição...", width=250)
        self.entry_pesquisa.pack(side="left", padx=(0, 10))
        self.entry_pesquisa.bind("<KeyRelease>", lambda e: self._atualizar_lista())

        nomes_categorias = ["Todas as categorias"] + [c.nome for c in self.categorias]
        self.combo_categoria = ctk.CTkComboBox(
            filtros, values=nomes_categorias, width=180, command=lambda v: self._atualizar_lista(),
            dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"),
        )
        self.combo_categoria.set("Todas as categorias")
        self.combo_categoria.pack(side="left", padx=(0, 10))

        self.entry_data_inicio = ctk.CTkEntry(filtros, placeholder_text="De (dd/mm/aaaa)", width=130)
        self.entry_data_inicio.pack(side="left", padx=(0, 10))

        self.entry_data_fim = ctk.CTkEntry(filtros, placeholder_text="Até (dd/mm/aaaa)", width=130)
        self.entry_data_fim.pack(side="left", padx=(0, 10))

        ctk.CTkButton(filtros, text="Filtrar", width=80, command=self._atualizar_lista).pack(side="left")

        # --- Lista ---
        self.lista_frame = ctk.CTkScrollableFrame(self)
        self.lista_frame.pack(fill="both", expand=True, padx=30, pady=(0, 25))

    def _atualizar_lista(self) -> None:
        for widget in self.lista_frame.winfo_children():
            widget.destroy()

        texto = self.entry_pesquisa.get()
        nome_cat = self.combo_categoria.get()
        categoria_id = next(
            (c.id for c in self.categorias if c.nome == nome_cat), None
        ) if nome_cat != "Todas as categorias" else None

        data_inicio = self._parse_data(self.entry_data_inicio.get())
        data_fim = self._parse_data(self.entry_data_fim.get())

        receitas = ReceitaController.listar(texto, categoria_id, data_inicio, data_fim)

        if not receitas:
            ctk.CTkLabel(self.lista_frame, text="Nenhuma receita encontrada.").pack(pady=20)
            return

        cabecalho = ctk.CTkFrame(self.lista_frame, fg_color="transparent")
        cabecalho.pack(fill="x", pady=(0, 5))
        for texto_col, largura in [("Data", 90), ("Descrição", 250), ("Categoria", 130), ("Valor", 120)]:
            ctk.CTkLabel(cabecalho, text=texto_col, width=largura, font=ctk.CTkFont(weight="bold")).pack(side="left")

        for receita in receitas:
            linha = ctk.CTkFrame(self.lista_frame, corner_radius=8)
            linha.pack(fill="x", pady=3)
            ctk.CTkLabel(linha, text=receita.data.strftime("%d/%m/%Y"), width=90).pack(side="left", padx=5, pady=8)
            ctk.CTkLabel(linha, text=receita.descricao, width=250, anchor="w").pack(side="left", pady=8)
            ctk.CTkLabel(linha, text=receita.categoria.nome, width=130).pack(side="left", pady=8)
            ctk.CTkLabel(
                linha, text=f"{self.moeda} {receita.valor:,.2f}", width=120, text_color="#2ECC71"
            ).pack(side="left", pady=8)
            ctk.CTkButton(
                linha, text="✏️", width=35, fg_color="transparent",
                command=lambda r=receita: self._abrir_formulario(r)
            ).pack(side="right", padx=3)
            ctk.CTkButton(
                linha, text="🗑️", width=35, fg_color="transparent", hover_color="#E74C3C",
                command=lambda r=receita: self._excluir(r)
            ).pack(side="right", padx=3)

    @staticmethod
    def _parse_data(texto: str):
        if not texto.strip():
            return None
        try:
            return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
        except ValueError:
            return None

    def _excluir(self, receita) -> None:
        if messagebox.askyesno("Confirmar", f"Excluir a receita '{receita.descricao}'?"):
            ReceitaController.excluir(receita.id, self.usuario.login)
            self._atualizar_lista()

    def _abrir_formulario(self, receita=None) -> None:
        FormularioReceita(self, receita, self.categorias, self.usuario, self._atualizar_lista)


class FormularioReceita(ctk.CTkToplevel):
    """Janela modal para criação/edição de receitas."""

    def __init__(self, master, receita, categorias, usuario, ao_salvar):
        super().__init__(master)
        self.receita = receita
        self.categorias = categorias
        self.usuario = usuario
        self.ao_salvar = ao_salvar

        self.title("Editar Receita" if receita else "Nova Receita")
        self.geometry("400x480")
        self.resizable(False, False)
        self.grab_set()
        self._construir_layout()

    def _construir_layout(self) -> None:
        ctk.CTkLabel(
            self, text=self.title(), font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 15))

        self.entry_descricao = ctk.CTkEntry(self, placeholder_text="Descrição", width=320)
        self.entry_descricao.pack(pady=8)

        self.entry_valor = ctk.CTkEntry(self, placeholder_text="Valor (ex: 150.00)", width=320)
        self.entry_valor.pack(pady=8)

        self.entry_data = ctk.CTkEntry(self, placeholder_text="Data (dd/mm/aaaa)", width=320)
        self.entry_data.pack(pady=8)

        self.combo_categoria = ctk.CTkComboBox(
            self, values=[c.nome for c in self.categorias], width=320,
            dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"),
        )
        self.combo_categoria.pack(pady=8)

        self.entry_obs = ctk.CTkTextbox(self, width=320, height=80)
        self.entry_obs.pack(pady=8)

        if self.receita:
            self.entry_descricao.insert(0, self.receita.descricao)
            self.entry_valor.insert(0, str(self.receita.valor))
            self.entry_data.insert(0, self.receita.data.strftime("%d/%m/%Y"))
            self.combo_categoria.set(self.receita.categoria.nome)
            self.entry_obs.insert("1.0", self.receita.observacoes)
        else:
            self.entry_data.insert(0, date.today().strftime("%d/%m/%Y"))
            if self.categorias:
                self.combo_categoria.set(self.categorias[0].nome)

        ctk.CTkButton(self, text="Salvar", width=320, command=self._salvar).pack(pady=20)

    def _salvar(self) -> None:
        try:
            valor = float(self.entry_valor.get().replace(",", "."))
            data_lanc = datetime.strptime(self.entry_data.get().strip(), "%d/%m/%Y").date()
            categoria = next(
                (c for c in self.categorias if c.nome == self.combo_categoria.get()), None
            )
            if not categoria:
                raise ValidationError("Selecione uma categoria válida.")

            if self.receita:
                ReceitaController.editar(
                    self.receita.id, self.entry_descricao.get(), valor, data_lanc,
                    categoria.id, self.entry_obs.get("1.0", "end").strip(), self.usuario.login,
                )
            else:
                ReceitaController.criar(
                    self.entry_descricao.get(), valor, data_lanc, categoria.id,
                    self.entry_obs.get("1.0", "end").strip(), self.usuario.login,
                )
            self.ao_salvar()
            self.destroy()
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Verifique os campos numéricos e de data.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

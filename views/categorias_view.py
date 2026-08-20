"""
views/categorias_view.py
Tela de gestão de categorias de receitas e despesas.
"""
import customtkinter as ctk
from tkinter import messagebox

from controllers.categoria_controller import CategoriaController
from utils.validators import ValidationError


class CategoriasView(ctk.CTkFrame):
    """CRUD de categorias, separadas por abas de Receita e Despesa."""

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self._construir_layout()

    def _construir_layout(self) -> None:
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=30, pady=(25, 10))
        ctk.CTkLabel(
            topo, text="Categorias", font=ctk.CTkFont(size=26, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(topo, text="+ Nova Categoria", command=self._abrir_formulario).pack(side="right")

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=30, pady=(0, 25))
        self.tabview.add("Despesas")
        self.tabview.add("Receitas")

        self.frame_despesas = ctk.CTkScrollableFrame(self.tabview.tab("Despesas"))
        self.frame_despesas.pack(fill="both", expand=True)

        self.frame_receitas = ctk.CTkScrollableFrame(self.tabview.tab("Receitas"))
        self.frame_receitas.pack(fill="both", expand=True)

        self._atualizar_lista()

    def _atualizar_lista(self) -> None:
        for widget in self.frame_despesas.winfo_children():
            widget.destroy()
        for widget in self.frame_receitas.winfo_children():
            widget.destroy()

        for categoria in CategoriaController.listar(tipo="despesa"):
            self._criar_linha(self.frame_despesas, categoria)
        for categoria in CategoriaController.listar(tipo="receita"):
            self._criar_linha(self.frame_receitas, categoria)

    def _criar_linha(self, master, categoria) -> None:
        linha = ctk.CTkFrame(master, corner_radius=8)
        linha.pack(fill="x", pady=3)

        ctk.CTkFrame(linha, fg_color=categoria.cor, width=18, height=18, corner_radius=4).pack(
            side="left", padx=10, pady=8
        )
        ctk.CTkLabel(linha, text=categoria.nome, anchor="w").pack(side="left", fill="x", expand=True, pady=8)
        ctk.CTkButton(
            linha, text="✏️", width=35, fg_color="transparent",
            command=lambda c=categoria: self._abrir_formulario(c)
        ).pack(side="right", padx=3)
        ctk.CTkButton(
            linha, text="🗑️", width=35, fg_color="transparent", hover_color="#E74C3C",
            command=lambda c=categoria: self._excluir(c)
        ).pack(side="right", padx=3)

    def _excluir(self, categoria) -> None:
        if messagebox.askyesno("Confirmar", f"Excluir a categoria '{categoria.nome}'?"):
            try:
                CategoriaController.excluir(categoria.id)
                self._atualizar_lista()
            except ValidationError as e:
                messagebox.showwarning("Atenção", str(e))

    def _abrir_formulario(self, categoria=None) -> None:
        FormularioCategoria(self, categoria, self._atualizar_lista)


class FormularioCategoria(ctk.CTkToplevel):
    """Janela modal para criação/edição de categorias."""

    CORES_DISPONIVEIS = [
        "#3498DB", "#2ECC71", "#E74C3C", "#E67E22", "#9B59B6",
        "#1ABC9C", "#F1C40F", "#7F8C8D", "#34495E", "#16A085",
    ]

    def __init__(self, master, categoria, ao_salvar):
        super().__init__(master)
        self.categoria = categoria
        self.ao_salvar = ao_salvar
        self.cor_selecionada = categoria.cor if categoria else self.CORES_DISPONIVEIS[0]

        self.title("Editar Categoria" if categoria else "Nova Categoria")
        self.geometry("360x400")
        self.resizable(False, False)
        self.grab_set()
        self._construir_layout()

    def _construir_layout(self) -> None:
        ctk.CTkLabel(
            self, text=self.title(), font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 15))

        self.entry_nome = ctk.CTkEntry(self, placeholder_text="Nome da categoria", width=280)
        self.entry_nome.pack(pady=8)
        if self.categoria:
            self.entry_nome.insert(0, self.categoria.nome)

        self.combo_tipo = ctk.CTkComboBox(
            self, values=["despesa", "receita"], width=280,
            dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"),
        )
        self.combo_tipo.pack(pady=8)
        self.combo_tipo.set(self.categoria.tipo if self.categoria else "despesa")
        if self.categoria:
            self.combo_tipo.configure(state="disabled")  # tipo não muda após criado

        ctk.CTkLabel(self, text="Cor:").pack(pady=(10, 5))
        cores_frame = ctk.CTkFrame(self, fg_color="transparent")
        cores_frame.pack()
        for cor in self.CORES_DISPONIVEIS:
            ctk.CTkButton(
                cores_frame, text="", width=25, height=25, fg_color=cor,
                border_width=2 if cor == self.cor_selecionada else 0,
                command=lambda c=cor: self._selecionar_cor(c)
            ).grid(row=0, column=self.CORES_DISPONIVEIS.index(cor), padx=3, pady=5)

        ctk.CTkButton(self, text="Salvar", width=280, command=self._salvar).pack(pady=25)

    def _selecionar_cor(self, cor: str) -> None:
        self.cor_selecionada = cor

    def _salvar(self) -> None:
        try:
            if self.categoria:
                CategoriaController.editar(self.categoria.id, self.entry_nome.get(), self.cor_selecionada)
            else:
                CategoriaController.criar(self.entry_nome.get(), self.combo_tipo.get(), self.cor_selecionada)
            self.ao_salvar()
            self.destroy()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

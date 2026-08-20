"""
views/metas_view.py
Tela de metas financeiras, com barra de progresso visual.
"""
from datetime import date, datetime

import customtkinter as ctk
from tkinter import messagebox

from controllers.meta_controller import MetaController
from controllers.config_controller import ConfigController
from utils.validators import ValidationError


class MetasView(ctk.CTkFrame):
    """Listagem e gerenciamento de metas financeiras com progresso."""

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self.moeda = ConfigController.obter("moeda")
        self._construir_layout()
        self._atualizar_lista()

    def _construir_layout(self) -> None:
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=30, pady=(25, 10))
        ctk.CTkLabel(
            topo, text="Metas Financeiras", font=ctk.CTkFont(size=26, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(topo, text="+ Nova Meta", command=self._abrir_formulario).pack(side="right")

        self.lista_frame = ctk.CTkScrollableFrame(self)
        self.lista_frame.pack(fill="both", expand=True, padx=30, pady=(0, 25))

    def _atualizar_lista(self) -> None:
        for widget in self.lista_frame.winfo_children():
            widget.destroy()

        metas = MetaController.listar()
        if not metas:
            ctk.CTkLabel(self.lista_frame, text="Nenhuma meta cadastrada.").pack(pady=20)
            return

        for meta in metas:
            card = ctk.CTkFrame(self.lista_frame, corner_radius=10)
            card.pack(fill="x", pady=6)

            topo_card = ctk.CTkFrame(card, fg_color="transparent")
            topo_card.pack(fill="x", padx=15, pady=(12, 5))
            status = "✅ Concluída" if meta.concluida else f"Prazo: {meta.prazo.strftime('%d/%m/%Y')}"
            ctk.CTkLabel(
                topo_card, text=meta.titulo, font=ctk.CTkFont(size=15, weight="bold")
            ).pack(side="left")
            ctk.CTkLabel(topo_card, text=status, text_color=("gray35","gray70")).pack(side="right")

            progresso = min(meta.valor_atual / meta.valor_alvo, 1.0) if meta.valor_alvo else 0
            barra = ctk.CTkProgressBar(card, width=500)
            barra.set(progresso)
            barra.pack(padx=15, pady=5, fill="x")

            rodape = ctk.CTkFrame(card, fg_color="transparent")
            rodape.pack(fill="x", padx=15, pady=(0, 12))
            ctk.CTkLabel(
                rodape,
                text=f"{self.moeda} {meta.valor_atual:,.2f} de {self.moeda} {meta.valor_alvo:,.2f} "
                     f"({progresso * 100:.0f}%)",
            ).pack(side="left")

            ctk.CTkButton(
                rodape, text="Atualizar progresso", width=150,
                command=lambda m=meta: self._atualizar_progresso(m)
            ).pack(side="right", padx=3)
            ctk.CTkButton(
                rodape, text="🗑️", width=35, fg_color="transparent", hover_color="#E74C3C",
                command=lambda m=meta: self._excluir(m)
            ).pack(side="right", padx=3)

    def _atualizar_progresso(self, meta) -> None:
        JanelaProgresso(self, meta, self.usuario, self._atualizar_lista)

    def _excluir(self, meta) -> None:
        if messagebox.askyesno("Confirmar", f"Excluir a meta '{meta.titulo}'?"):
            MetaController.excluir(meta.id, self.usuario.login)
            self._atualizar_lista()

    def _abrir_formulario(self) -> None:
        FormularioMeta(self, self.usuario, self._atualizar_lista)


class FormularioMeta(ctk.CTkToplevel):
    """Janela modal para criação de metas financeiras."""

    def __init__(self, master, usuario, ao_salvar):
        super().__init__(master)
        self.usuario = usuario
        self.ao_salvar = ao_salvar
        self.title("Nova Meta")
        self.geometry("360x360")
        self.resizable(False, False)
        self.grab_set()
        self._construir_layout()

    def _construir_layout(self) -> None:
        ctk.CTkLabel(
            self, text="Nova Meta Financeira", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 15))

        self.entry_titulo = ctk.CTkEntry(self, placeholder_text="Título (ex: Viagem de férias)", width=280)
        self.entry_titulo.pack(pady=8)

        self.entry_valor = ctk.CTkEntry(self, placeholder_text="Valor alvo (ex: 2000.00)", width=280)
        self.entry_valor.pack(pady=8)

        self.entry_prazo = ctk.CTkEntry(self, placeholder_text="Prazo (dd/mm/aaaa)", width=280)
        self.entry_prazo.pack(pady=8)

        ctk.CTkButton(self, text="Salvar", width=280, command=self._salvar).pack(pady=25)

    def _salvar(self) -> None:
        try:
            valor = float(self.entry_valor.get().replace(",", "."))
            prazo = datetime.strptime(self.entry_prazo.get().strip(), "%d/%m/%Y").date()
            MetaController.criar(self.entry_titulo.get(), valor, prazo, self.usuario.login)
            self.ao_salvar()
            self.destroy()
        except (ValueError, ValidationError) as e:
            messagebox.showwarning(
                "Atenção", str(e) if isinstance(e, ValidationError) else "Verifique valor e data informados."
            )
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")


class JanelaProgresso(ctk.CTkToplevel):
    """Janela modal para atualizar o valor acumulado de uma meta."""

    def __init__(self, master, meta, usuario, ao_salvar):
        super().__init__(master)
        self.meta = meta
        self.usuario = usuario
        self.ao_salvar = ao_salvar
        self.title(f"Progresso: {meta.titulo}")
        self.geometry("320x200")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(self, text="Valor economizado até agora:").pack(pady=(20, 5))
        self.entry_valor = ctk.CTkEntry(self, width=240)
        self.entry_valor.insert(0, str(meta.valor_atual))
        self.entry_valor.pack(pady=5)

        ctk.CTkButton(self, text="Salvar", width=240, command=self._salvar).pack(pady=20)

    def _salvar(self) -> None:
        try:
            valor = float(self.entry_valor.get().replace(",", "."))
            MetaController.atualizar_progresso(self.meta.id, valor, self.usuario.login)
            self.ao_salvar()
            self.destroy()
        except ValueError:
            messagebox.showwarning("Atenção", "Informe um valor numérico válido.")
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))

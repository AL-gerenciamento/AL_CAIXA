"""
views/historico_vendas_view.py
Histórico de vendas: lista as vendas em aberto (carrinhos deixados pendentes,
com opção de continuar, fechar ou descartar) e o histórico de vendas já
fechadas. Vendas fechadas há mais de 3 meses são removidas automaticamente
(controllers/venda_controller.py) para não acumular histórico sem limite.
"""
import customtkinter as ctk
from tkinter import messagebox

from controllers.venda_controller import VendaController
from controllers.config_controller import ConfigController
from models import Permissao
from utils.validators import ValidationError


class HistoricoVendasView(ctk.CTkFrame):

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self.moeda = ConfigController.obter("moeda")
        self._construir_layout()
        self._carregar()

    def _construir_layout(self) -> None:
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=30, pady=(25, 10))
        ctk.CTkLabel(topo, text="Histórico de Vendas", font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        ctk.CTkButton(topo, text="🔄 Atualizar", width=110, command=self._carregar).pack(side="right")

        ctk.CTkLabel(
            self, text="🕒 Vendas em aberto", font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=30, pady=(10, 0))
        self.frame_abertas = ctk.CTkScrollableFrame(self, height=180)
        self.frame_abertas.pack(fill="x", padx=30, pady=(5, 15))

        ctk.CTkLabel(
            self, text="📜 Vendas fechadas (últimos 3 meses)", font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=30, pady=(0, 0))
        self.frame_fechadas = ctk.CTkScrollableFrame(self)
        self.frame_fechadas.pack(fill="both", expand=True, padx=30, pady=(5, 25))

    def _carregar(self) -> None:
        self._carregar_abertas()
        self._carregar_fechadas()

    def _carregar_abertas(self) -> None:
        for w in self.frame_abertas.winfo_children():
            w.destroy()
        abertas = VendaController.listar_abertas()
        if not abertas:
            ctk.CTkLabel(self.frame_abertas, text="Nenhuma venda em aberto.", text_color="gray").pack(
                anchor="w", padx=8, pady=8
            )
            return
        for venda in abertas:
            self._linha_aberta(venda)

    def _linha_aberta(self, venda) -> None:
        linha = ctk.CTkFrame(self.frame_abertas, corner_radius=8)
        linha.pack(fill="x", pady=3)

        qtd_itens = len(venda.itens)
        texto = (
            f"Venda nº {venda.numero_venda}  •  {venda.data_hora.strftime('%d/%m/%Y %H:%M')}  •  "
            f"{qtd_itens} item(ns)  •  {self.moeda} {venda.valor_total:,.2f}"
        )
        if venda.cliente:
            texto += f"  •  Cliente: {venda.cliente}"
        ctk.CTkLabel(linha, text=texto, anchor="w").pack(side="left", padx=10, pady=10, fill="x", expand=True)

        ctk.CTkButton(
            linha, text="▶️ Continuar", width=110, fg_color="#2ECC71", hover_color="#27AE60",
            command=lambda v=venda: self._continuar(v),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            linha, text="✅ Fechar", width=90,
            command=lambda v=venda: self._fechar(v),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            linha, text="🗑️ Descartar", width=100, fg_color="transparent", border_width=1,
            hover_color="#E74C3C", command=lambda v=venda: self._descartar(v),
        ).pack(side="left", padx=4)

    def _continuar(self, venda) -> None:
        app = self.winfo_toplevel()
        if not hasattr(app, "_navegar"):
            messagebox.showerror("Erro", "Não foi possível abrir o caixa a partir daqui.")
            return
        app._navegar("Caixa / Venda")
        tela_pdv = app.tela_atual
        if hasattr(tela_pdv, "carregar_venda_aberta"):
            tela_pdv.carregar_venda_aberta(venda)

    def _fechar(self, venda) -> None:
        app = self.winfo_toplevel()
        if not hasattr(app, "_navegar"):
            messagebox.showerror("Erro", "Não foi possível abrir o caixa a partir daqui.")
            return
        app._navegar("Caixa / Venda")
        tela_pdv = app.tela_atual
        if hasattr(tela_pdv, "carregar_venda_aberta"):
            tela_pdv.carregar_venda_aberta(venda, ir_direto_ao_pagamento=True)

    def _descartar(self, venda) -> None:
        if not messagebox.askyesno(
            "Descartar venda", f"Descartar a venda em aberto nº {venda.numero_venda}? Essa ação não pode ser desfeita."
        ):
            return
        try:
            VendaController.descartar_aberta(venda.id, self.usuario.login)
            self._carregar_abertas()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    def _carregar_fechadas(self) -> None:
        for w in self.frame_fechadas.winfo_children():
            w.destroy()
        fechadas = VendaController.listar_historico()
        if not fechadas:
            ctk.CTkLabel(self.frame_fechadas, text="Nenhuma venda no histórico.", text_color="gray").pack(
                anchor="w", padx=8, pady=8
            )
            return
        for venda in fechadas:
            self._linha_fechada(venda)

    def _linha_fechada(self, venda) -> None:
        linha = ctk.CTkFrame(self.frame_fechadas, corner_radius=8)
        linha.pack(fill="x", pady=3)

        status = "Cancelada" if venda.cancelada else venda.forma_pagamento
        cor = "#E74C3C" if venda.cancelada else ("gray35", "gray70")
        texto = (
            f"Venda nº {venda.numero_venda}  •  {venda.data_hora.strftime('%d/%m/%Y %H:%M')}  •  "
            f"{self.moeda} {venda.valor_total:,.2f}"
        )
        if venda.cliente:
            texto += f"  •  Cliente: {venda.cliente}"
        ctk.CTkLabel(linha, text=texto, anchor="w").pack(side="left", padx=10, pady=10, fill="x", expand=True)
        ctk.CTkLabel(linha, text=status, text_color=cor, width=140).pack(side="right", padx=10)
        if self.usuario.permissao == Permissao.ADMIN and (venda.desconto_percentual or venda.acrescimo_percentual):
            ctk.CTkButton(
                linha, text="🔍 Detalhes", width=100, fg_color="transparent", border_width=1,
                command=lambda v=venda: self._mostrar_detalhes(v),
            ).pack(side="right", padx=5)

    def _mostrar_detalhes(self, venda) -> None:
        janela = ctk.CTkToplevel(self)
        janela.title(f"Venda nº {venda.numero_venda} — Detalhes")
        janela.geometry("420x320")
        janela.transient(self.winfo_toplevel())
        janela.grab_set()

        ctk.CTkLabel(
            janela, text=f"Venda nº {venda.numero_venda}", font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(20, 10))

        def linha_info(rotulo, valor):
            f = ctk.CTkFrame(janela, fg_color="transparent")
            f.pack(fill="x", padx=20, pady=2)
            ctk.CTkLabel(f, text=rotulo, anchor="w").pack(side="left")
            ctk.CTkLabel(f, text=valor, anchor="e", font=ctk.CTkFont(weight="bold")).pack(side="right")

        linha_info("Subtotal:", f"{self.moeda} {venda.subtotal:,.2f}")
        if venda.desconto_percentual:
            valor_desconto = venda.subtotal * venda.desconto_percentual / 100
            linha_info(f"Desconto ({venda.desconto_percentual:g}%):", f"-{self.moeda} {valor_desconto:,.2f}")
        if venda.acrescimo_percentual:
            valor_acrescimo = venda.subtotal * venda.acrescimo_percentual / 100
            linha_info(f"Acréscimo ({venda.acrescimo_percentual:g}%):", f"+{self.moeda} {valor_acrescimo:,.2f}")
        linha_info("Total:", f"{self.moeda} {venda.valor_total:,.2f}")

        if venda.justificativa_acrescimo:
            ctk.CTkLabel(
                janela, text="Justificativa do acréscimo:", font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w", padx=20, pady=(15, 2))
            ctk.CTkLabel(
                janela, text=venda.justificativa_acrescimo, anchor="w", justify="left", wraplength=380,
            ).pack(anchor="w", padx=20, pady=(0, 10))

        ctk.CTkButton(janela, text="Fechar", command=janela.destroy).pack(pady=15)

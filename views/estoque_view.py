"""
views/estoque_view.py
Controle de prateleira, transferências entre estoques (Venda/Produção/
Prateleira) e produção de itens compostos. Itens 11, 13, 14 e 15.
"""
import customtkinter as ctk
from tkinter import messagebox, simpledialog

from controllers.produto_controller import ProdutoController
from controllers.estoque_controller import EstoqueController
from controllers.producao_controller import ProducaoController
from utils.validators import ValidationError, ajustar_quantidade_para_unidade

ESTOQUES_LABEL = {
    "venda": "Venda", "producao": "Produção Interna", "prateleira": "Prateleira",
    "compra": "Compra/Entrada",
}


class EstoqueView(ctk.CTkFrame):
    """Abas: Prateleira, Transferências e Produção."""

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self._construir_layout()

    def _construir_layout(self) -> None:
        ctk.CTkLabel(self, text="Estoque e Produção", font=ctk.CTkFont(size=26, weight="bold")).pack(
            anchor="w", padx=30, pady=(25, 10)
        )
        abas = ctk.CTkTabview(self)
        abas.pack(fill="both", expand=True, padx=30, pady=(0, 25))

        self._aba_prateleira = abas.add("Prateleira")
        self._aba_transferencia = abas.add("Transferências")
        self._aba_producao = abas.add("Produção")

        for construtor, aba in (
            (self._construir_prateleira, self._aba_prateleira),
            (self._construir_transferencia, self._aba_transferencia),
            (self._construir_producao, self._aba_producao),
        ):
            try:
                construtor(aba)
            except Exception as e:
                from utils.logger import registrar_erro
                registrar_erro(e, f"estoque_view.{construtor.__name__}")
                ctk.CTkLabel(
                    aba, text=f"Não foi possível carregar esta aba: {e}",
                    text_color="#E74C3C", wraplength=600,
                ).pack(pady=30, padx=20)

    # --- Prateleira ---
    def _construir_prateleira(self, aba) -> None:
        self.lista_prateleira = ctk.CTkScrollableFrame(aba)
        self.lista_prateleira.pack(fill="both", expand=True, padx=10, pady=10)
        self._atualizar_prateleira()

    def _atualizar_prateleira(self) -> None:
        for w in self.lista_prateleira.winfo_children():
            w.destroy()
        produtos = [p for p in ProdutoController.listar() if not p.composto or p.estoque_prateleira]

        cab = ctk.CTkFrame(self.lista_prateleira, fg_color="transparent")
        cab.pack(fill="x", pady=(0, 5))
        for texto, largura in [("Produto", 220), ("Estoque venda", 110), ("Prateleira", 110)]:
            ctk.CTkLabel(cab, text=texto, width=largura, font=ctk.CTkFont(weight="bold")).pack(side="left")

        for produto in produtos:
            linha = ctk.CTkFrame(self.lista_prateleira, corner_radius=8)
            linha.pack(fill="x", pady=3)
            ctk.CTkLabel(linha, text=produto.nome, width=220, anchor="w").pack(side="left", padx=5, pady=8)
            ctk.CTkLabel(linha, text=f"{produto.estoque_venda:g}", width=110).pack(side="left")
            ctk.CTkLabel(linha, text=f"{produto.estoque_prateleira:g}", width=110).pack(side="left")
            ctk.CTkButton(
                linha, text="Repor", width=80,
                command=lambda p=produto: self._mover_prateleira(p, repor=True)
            ).pack(side="right", padx=5)
            ctk.CTkButton(
                linha, text="Retornar", width=80,
                command=lambda p=produto: self._mover_prateleira(p, repor=False)
            ).pack(side="right", padx=5)
            ctk.CTkButton(
                linha, text="📥 Adicionar Estoque", width=150, fg_color="#2ECC71", hover_color="#27AE60",
                command=lambda p=produto: self._adicionar_estoque(p)
            ).pack(side="right", padx=5)

    def _adicionar_estoque(self, produto) -> None:
        qtd = simpledialog.askfloat(
            "Entrada de Estoque", f"Quantidade de '{produto.nome}' a adicionar ({produto.unidade_medida}):",
            parent=self, minvalue=0.001,
        )
        if not qtd:
            return
        qtd = ajustar_quantidade_para_unidade(qtd, produto.unidade_medida)
        try:
            EstoqueController.entrada(
                produto.id, qtd, motivo="Entrada manual de estoque",
                usuario_id=self.usuario.id, usuario=self.usuario.login,
            )
            self._atualizar_prateleira()
            messagebox.showinfo("Sucesso", f"+{qtd:g} {produto.unidade_medida} adicionados ao estoque de {produto.nome}.")
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Quantidade inválida.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    def _mover_prateleira(self, produto, repor: bool) -> None:
        titulo = "Repor na prateleira" if repor else "Retornar ao estoque"
        qtd = self._pedir_quantidade(titulo, produto.nome)
        if qtd is None:
            return
        qtd = ajustar_quantidade_para_unidade(qtd, produto.unidade_medida)
        try:
            if repor:
                EstoqueController.repor_prateleira(produto.id, qtd, self.usuario.id, self.usuario.login)
            else:
                EstoqueController.retornar_ao_estoque(produto.id, qtd, self.usuario.id, self.usuario.login)
            self._atualizar_prateleira()
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Quantidade inválida.")

    def _pedir_quantidade(self, titulo, nome_produto):
        from tkinter import simpledialog
        valor = simpledialog.askfloat(titulo, f"Quantidade de '{nome_produto}':", parent=self)
        return valor

    # --- Transferências manuais entre estoques ---
    def _construir_transferencia(self, aba) -> None:
        self.produtos_transf = ProdutoController.listar()
        nomes = [p.nome for p in self.produtos_transf]

        ctk.CTkLabel(aba, text="Transferir entre estoques", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 10))
        self.combo_produto_transf = ctk.CTkComboBox(aba, values=nomes, width=380)
        if nomes:
            self.combo_produto_transf.set(nomes[0])
        self.combo_produto_transf.pack(pady=6)

        linha = ctk.CTkFrame(aba, fg_color="transparent")
        linha.pack(pady=6)
        opcoes = [ESTOQUES_LABEL[k] for k in ("venda", "producao", "prateleira")]
        self.combo_origem = ctk.CTkComboBox(linha, values=opcoes, width=180)
        self.combo_origem.set(opcoes[0])
        self.combo_origem.pack(side="left", padx=5)
        ctk.CTkLabel(linha, text="→").pack(side="left", padx=5)
        self.combo_destino = ctk.CTkComboBox(linha, values=opcoes, width=180)
        self.combo_destino.set(opcoes[1])
        self.combo_destino.pack(side="left", padx=5)

        self.entry_qtd_transf = ctk.CTkEntry(aba, placeholder_text="Quantidade", width=380)
        self.entry_qtd_transf.pack(pady=6)
        self.entry_motivo_transf = ctk.CTkEntry(aba, placeholder_text="Motivo", width=380)
        self.entry_motivo_transf.pack(pady=6)
        ctk.CTkButton(aba, text="Transferir", width=380, command=self._transferir).pack(pady=15)

        self.lista_movimentos = ctk.CTkScrollableFrame(aba, label_text="Últimas movimentações")
        self.lista_movimentos.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._atualizar_movimentos()

    def _transferir(self) -> None:
        try:
            produto = next((p for p in self.produtos_transf if p.nome == self.combo_produto_transf.get()), None)
            if not produto:
                raise ValidationError("Selecione um produto válido.")
            origem = next(k for k, v in ESTOQUES_LABEL.items() if v == self.combo_origem.get())
            destino = next(k for k, v in ESTOQUES_LABEL.items() if v == self.combo_destino.get())
            quantidade = float((self.entry_qtd_transf.get() or "0").replace(",", "."))
            quantidade = ajustar_quantidade_para_unidade(quantidade, produto.unidade_medida)
            EstoqueController.transferir(
                produto.id, origem, destino, quantidade, self.entry_motivo_transf.get(),
                self.usuario.id, self.usuario.login,
            )
            self.entry_qtd_transf.delete(0, "end")
            self.entry_motivo_transf.delete(0, "end")
            self._atualizar_movimentos()
            self._atualizar_prateleira()
            messagebox.showinfo("Sucesso", "Transferência realizada.")
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Quantidade inválida.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    def _atualizar_movimentos(self) -> None:
        for w in self.lista_movimentos.winfo_children():
            w.destroy()
        for mov in EstoqueController.historico_movimentos(limite=30):
            texto = (
                f"{mov.data_hora.strftime('%d/%m %H:%M')} - {mov.produto.nome}: "
                f"{mov.quantidade:g} ({ESTOQUES_LABEL.get(mov.origem, mov.origem)} → {ESTOQUES_LABEL.get(mov.destino, mov.destino)})"
                + (f" - {mov.motivo}" if mov.motivo else "")
            )
            ctk.CTkLabel(self.lista_movimentos, text=texto, anchor="w").pack(fill="x", pady=2)

    # --- Produção ---
    def _construir_producao(self, aba) -> None:
        self.compostos = [p for p in ProdutoController.listar() if p.composto]
        nomes = [p.nome for p in self.compostos]

        ctk.CTkLabel(aba, text="Produzir item composto", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 10))
        self.combo_produto_prod = ctk.CTkComboBox(aba, values=nomes, width=380, command=lambda v: self._atualizar_producivel())
        if nomes:
            self.combo_produto_prod.set(nomes[0])
        self.combo_produto_prod.pack(pady=6)

        self.label_producivel = ctk.CTkLabel(aba, text="")
        self.label_producivel.pack(pady=4)

        self.entry_qtd_prod = ctk.CTkEntry(aba, placeholder_text="Quantidade a produzir", width=380)
        self.entry_qtd_prod.pack(pady=6)
        ctk.CTkButton(aba, text="Produzir", width=380, command=self._produzir).pack(pady=15)

        self.lista_resumo_producao = ctk.CTkScrollableFrame(aba, label_text="Resumo de produção")
        self.lista_resumo_producao.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._atualizar_producivel()
        self._atualizar_resumo_producao()

    def _atualizar_producivel(self, *_):
        produto = next((p for p in self.compostos if p.nome == self.combo_produto_prod.get()), None)
        if produto:
            qtd = ProducaoController.quantidade_producivel(produto.id)
            self.label_producivel.configure(text=f"Pode produzir agora: {qtd:g} {produto.unidade_medida}")

    def _produzir(self) -> None:
        try:
            produto = next((p for p in self.compostos if p.nome == self.combo_produto_prod.get()), None)
            if not produto:
                raise ValidationError("Selecione um produto composto válido.")
            quantidade = float((self.entry_qtd_prod.get() or "0").replace(",", "."))
            quantidade = ajustar_quantidade_para_unidade(quantidade, produto.unidade_medida)
            ProducaoController.produzir(produto.id, quantidade, self.usuario.id, self.usuario.login)
            self.entry_qtd_prod.delete(0, "end")
            self._atualizar_producivel()
            self._atualizar_resumo_producao()
            messagebox.showinfo("Sucesso", f"Produção de {quantidade:g}x {produto.nome} registrada.")
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Quantidade inválida.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    def _atualizar_resumo_producao(self) -> None:
        for w in self.lista_resumo_producao.winfo_children():
            w.destroy()
        for item in ProducaoController.resumo_producao():
            texto = (
                f"{item['produto']}: {item['quantidade_produzida_total']:g} produzidas ao todo | "
                f"{item['producivel_agora']:g} ainda podem ser produzidas agora"
            )
            ctk.CTkLabel(self.lista_resumo_producao, text=texto, anchor="w").pack(fill="x", pady=2)

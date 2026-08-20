"""
views/pdv_view.py
Ponto de venda: leitura de produto por código/nome, carrinho, finalização
com baixa automática de estoque e caixa, saída de caixa e recibo
(impressão/PDF/WhatsApp). Itens 2, 3, 4, 5 e 16 da especificação.
"""
import os
import subprocess
import sys

import io

import customtkinter as ctk
from tkinter import messagebox, simpledialog
from PIL import Image

from controllers.produto_controller import ProdutoController
from controllers.venda_controller import VendaController
from controllers.caixa_controller import CaixaController
from controllers.recibo_controller import ReciboController
from controllers.config_controller import ConfigController
from controllers.pix_controller import PixController, PixNaoConfiguradoError
from utils.validators import ValidationError, ajustar_quantidade_para_unidade
from utils.impressora import imprimir_pdf_direto

FORMAS_PAGAMENTO = ["Dinheiro", "Cartão de Débito", "Cartão de Crédito", "PIX", "QR Code", "Outro"]


class PdvView(ctk.CTkFrame):
    """Tela de venda (caixa)."""

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self.moeda = ConfigController.obter("moeda")
        self.carrinho: list[dict] = []
        self.venda_aberta_id: int | None = None
        self._construir_layout()
        self._atualizar_resumo_caixa()

    def _construir_layout(self) -> None:
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=30, pady=(25, 10))
        ctk.CTkLabel(topo, text="Caixa / Venda", font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        self.label_venda_aberta = ctk.CTkLabel(
            topo, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color="#F39C12",
        )
        self.label_venda_aberta.pack(side="left", padx=15)
        self.label_saldo = ctk.CTkLabel(topo, text="", font=ctk.CTkFont(size=14))
        self.label_saldo.pack(side="right")
        ctk.CTkButton(topo, text="Saída de Caixa", fg_color="#E74C3C", command=self._abrir_saida).pack(side="right", padx=10)

        busca_frame = ctk.CTkFrame(self, fg_color="transparent")
        busca_frame.pack(fill="x", padx=30, pady=(0, 0))
        linha_busca = ctk.CTkFrame(busca_frame, fg_color="transparent")
        linha_busca.pack(fill="x")
        self.entry_codigo = ctk.CTkEntry(
            linha_busca, placeholder_text="Código de barras, código interno ou nome do produto (Enter para adicionar)",
            width=520,
        )
        self.entry_codigo.pack(side="left", padx=(0, 10))
        self.entry_codigo.bind("<Return>", lambda e: self._adicionar_por_codigo())
        self.entry_codigo.bind("<KeyRelease>", self._ao_digitar_busca)
        self.entry_codigo.bind("<Button-1>", lambda e: self._mostrar_sugestoes(self.entry_codigo.get()))
        self.entry_codigo.bind("<FocusOut>", lambda e: self.after(150, self._ocultar_sugestoes))
        ctk.CTkButton(linha_busca, text="Adicionar", command=self._adicionar_por_codigo).pack(side="left")

        self.frame_sugestoes = ctk.CTkScrollableFrame(busca_frame, fg_color=("gray95", "gray17"), height=170)

        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.pack(fill="both", expand=True, padx=30, pady=(10, 25))

        self.carrinho_frame = ctk.CTkScrollableFrame(corpo, label_text="Itens da venda")
        self.carrinho_frame.pack(side="left", fill="both", expand=True, padx=(0, 15))

        lateral = ctk.CTkFrame(corpo, width=280)
        lateral.pack(side="right", fill="y")
        lateral.pack_propagate(False)

        self.frame_form = ctk.CTkFrame(lateral, fg_color="transparent")
        self.frame_form.pack(fill="both", expand=True)

        self.entry_cliente = ctk.CTkEntry(self.frame_form, placeholder_text="Cliente (opcional)")
        self.entry_cliente.pack(padx=15, pady=(20, 8), fill="x")

        ctk.CTkLabel(self.frame_form, text="Forma(s) de pagamento", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=15, pady=(5, 0)
        )
        self.frame_pagamentos = ctk.CTkFrame(self.frame_form, fg_color="transparent")
        self.frame_pagamentos.pack(padx=15, pady=(2, 0), fill="x")
        self.linhas_pagamento: list[dict] = []
        self._adicionar_linha_pagamento()
        ctk.CTkButton(
            self.frame_form, text="+ Adicionar forma de pagamento", fg_color="transparent",
            border_width=1, height=28, command=self._adicionar_linha_pagamento,
        ).pack(padx=15, pady=(4, 8), fill="x")

        desconto_frame = ctk.CTkFrame(self.frame_form, fg_color="transparent")
        desconto_frame.pack(padx=15, pady=(4, 0), fill="x")
        ctk.CTkLabel(desconto_frame, text="Desconto (%)", width=90, anchor="w").pack(side="left")
        self.entry_desconto = ctk.CTkEntry(desconto_frame, placeholder_text="0")
        self.entry_desconto.pack(side="left", fill="x", expand=True)
        self.entry_desconto.bind("<KeyRelease>", lambda e: self._atualizar_falta_pagar())

        acrescimo_frame = ctk.CTkFrame(self.frame_form, fg_color="transparent")
        acrescimo_frame.pack(padx=15, pady=(6, 0), fill="x")
        ctk.CTkLabel(acrescimo_frame, text="Acréscimo (%)", width=90, anchor="w").pack(side="left")
        self.entry_acrescimo = ctk.CTkEntry(acrescimo_frame, placeholder_text="0")
        self.entry_acrescimo.pack(side="left", fill="x", expand=True)
        self.entry_acrescimo.bind("<KeyRelease>", self._ao_alterar_acrescimo)

        self.frame_justificativa_acrescimo = ctk.CTkFrame(self.frame_form, fg_color="transparent")
        self.entry_justificativa_acrescimo = ctk.CTkEntry(
            self.frame_justificativa_acrescimo, placeholder_text="Justificativa do acréscimo (obrigatória)",
        )
        self.entry_justificativa_acrescimo.pack(fill="x")

        self.subtotal_desconto_acrescimo_visivel = False

        self.label_subtotal = ctk.CTkLabel(
            self.frame_form, text="", font=ctk.CTkFont(size=12), text_color=("gray35", "gray70"),
        )
        self.label_subtotal.pack(pady=(8, 0))

        self.label_total = ctk.CTkLabel(self.frame_form, text=f"{self.moeda} 0,00", font=ctk.CTkFont(size=26, weight="bold"))
        self.label_total.pack(pady=(2, 0))
        self.label_falta = ctk.CTkLabel(
            self.frame_form, text="", font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E74C3C", wraplength=240, justify="center",
        )
        self.label_falta.pack(pady=(0, 15))

        ctk.CTkButton(self.frame_form, text="Finalizar Venda", height=45, command=self._finalizar_venda).pack(padx=15, pady=8, fill="x")
        ctk.CTkButton(
            self.frame_form, text="⏸️ Deixar em Aberto (continuar depois)", fg_color="#F39C12", hover_color="#D68910",
            command=self._deixar_em_aberto,
        ).pack(padx=15, pady=8, fill="x")
        ctk.CTkButton(self.frame_form, text="Limpar Carrinho", fg_color="transparent", border_width=1,
                      command=self._limpar_carrinho).pack(padx=15, pady=8, fill="x")

        self.frame_pos_venda = ctk.CTkFrame(lateral, fg_color="transparent")

    def _adicionar_linha_pagamento(self) -> None:
        linha = ctk.CTkFrame(self.frame_pagamentos, fg_color="transparent")
        linha.pack(fill="x", pady=(3, 8))

        linha_topo = ctk.CTkFrame(linha, fg_color="transparent")
        linha_topo.pack(fill="x")
        linha_baixo = ctk.CTkFrame(linha, fg_color="transparent")
        linha_baixo.pack(fill="x", pady=(4, 0))

        registro = {"linha": linha}

        combo = ctk.CTkComboBox(
            linha_topo, values=FORMAS_PAGAMENTO,
            command=lambda _v, r=registro: self._alternar_botao_qr(r),
        )
        combo.set(FORMAS_PAGAMENTO[0])
        combo.pack(side="left", fill="x", expand=True)

        btn_remover = ctk.CTkButton(
            linha_topo, text="🗑️", width=30, fg_color="transparent", hover_color="#E74C3C",
            command=lambda r=registro: self._remover_linha_pagamento(r),
        )
        btn_remover.pack(side="left", padx=(5, 0))

        entry_valor = ctk.CTkEntry(linha_baixo, placeholder_text="Valor (R$)")
        entry_valor.pack(side="left", fill="x", expand=True)
        entry_valor.bind("<KeyRelease>", lambda e: self._atualizar_falta_pagar())

        btn_pix = ctk.CTkButton(
            linha_baixo, text="Ver QR Code", width=100, fg_color="#3498DB", hover_color="#2980B9",
            command=lambda r=registro: self._abrir_qr_pix(r),
        )
        btn_qr_generico = ctk.CTkButton(
            linha_baixo, text="Gerar QR Code", width=115, fg_color="#3498DB", hover_color="#2980B9",
            command=lambda r=registro: self._abrir_qr_generico(r),
        )

        registro.update({
            "combo": combo, "entry": entry_valor, "btn_pix": btn_pix, "btn_qr_generico": btn_qr_generico,
        })

        self.linhas_pagamento.append(registro)
        self._alternar_botao_qr(registro)

    def _alternar_botao_qr(self, registro: dict) -> None:
        """Mostra o botão de QR Code adequado conforme a forma de pagamento escolhida."""
        forma = registro["combo"].get()
        registro["btn_pix"].pack_forget()
        registro["btn_qr_generico"].pack_forget()
        if forma == "PIX":
            registro["btn_pix"].pack(side="left", padx=(5, 0))
        elif forma == "QR Code":
            registro["btn_qr_generico"].pack(side="left", padx=(5, 0))
        self._atualizar_falta_pagar()

    def _abrir_qr_pix(self, registro: dict) -> None:
        texto_valor = (registro["entry"].get() or "0").strip().replace(",", ".")
        try:
            valor = float(texto_valor)
        except ValueError:
            valor = 0.0
        if valor <= 0:
            messagebox.showwarning("Atenção", "Informe o valor do pagamento Pix antes de gerar o QR Code.")
            return
        try:
            png_bytes = PixController.gerar_qrcode_bytes(valor)
        except PixNaoConfiguradoError as e:
            messagebox.showwarning("Pix não configurado", str(e))
            return
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível gerar o QR Code: {e}")
            return
        self._mostrar_janela_qr(f"{self.moeda} {valor:,.2f}", png_bytes)

    def _abrir_qr_generico(self, registro: dict) -> None:
        """
        Permite pagar com qualquer QR Code: o caixa cola o código Pix de outra
        chave, um link de pagamento (Mercado Pago, PicPay, etc.) ou qualquer
        texto, e o sistema gera a imagem do QR Code na hora para o cliente escanear.
        """
        codigo = simpledialog.askstring(
            "Gerar QR Code",
            "Cole aqui o código Pix (copia e cola), link de pagamento ou qualquer\n"
            "texto que deva virar um QR Code para o cliente escanear:",
            parent=self,
        )
        if not codigo:
            return
        try:
            png_bytes = PixController.gerar_qrcode_de_texto(codigo)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível gerar o QR Code: {e}")
            return
        self._mostrar_janela_qr("Escaneie para pagar", png_bytes)

    def _mostrar_janela_qr(self, titulo: str, png_bytes: bytes) -> None:
        janela = ctk.CTkToplevel(self)
        janela.title("Pagamento via QR Code")
        janela.geometry("340x430")
        janela.resizable(False, False)
        janela.grab_set()

        ctk.CTkLabel(janela, text=titulo, font=ctk.CTkFont(size=20, weight="bold"), wraplength=300).pack(pady=(20, 10))

        imagem = Image.open(io.BytesIO(png_bytes))
        ctk_img = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=(260, 260))
        ctk.CTkLabel(janela, text="", image=ctk_img).pack(pady=5)

        ctk.CTkLabel(
            janela, text="Escaneie com o app do banco ou de pagamento para pagar.", text_color=("gray35", "gray70")
        ).pack(pady=(5, 15))
        ctk.CTkButton(janela, text="Fechar", command=janela.destroy).pack(pady=(0, 15))

    def _remover_linha_pagamento(self, registro: dict) -> None:
        if len(self.linhas_pagamento) <= 1:
            return  # sempre precisa haver ao menos uma forma de pagamento
        registro["linha"].destroy()
        self.linhas_pagamento.remove(registro)
        self._atualizar_falta_pagar()

    def _limpar_linhas_pagamento(self) -> None:
        for registro in self.linhas_pagamento:
            registro["linha"].destroy()
        self.linhas_pagamento = []
        self._adicionar_linha_pagamento()

    def _preencher_valor_pagamento_unico(self, total: float) -> None:
        """Se só houver uma forma de pagamento, preenche o valor com o total automaticamente."""
        if len(self.linhas_pagamento) == 1:
            entry = self.linhas_pagamento[0]["entry"]
            entry.delete(0, "end")
            entry.insert(0, f"{total:.2f}")
        self._atualizar_falta_pagar()

    def _subtotal_carrinho(self) -> float:
        return sum(i["produto"].preco_venda * i["quantidade"] for i in self.carrinho)

    def _percentuais_desconto_acrescimo(self) -> tuple[float, float]:
        def _num(entry):
            texto = (entry.get() or "0").strip().replace(",", ".")
            try:
                return max(0.0, float(texto))
            except ValueError:
                return 0.0
        return _num(self.entry_desconto), _num(self.entry_acrescimo)

    def _total_carrinho(self) -> float:
        subtotal = self._subtotal_carrinho()
        desconto_pct, acrescimo_pct = self._percentuais_desconto_acrescimo()
        return subtotal - (subtotal * desconto_pct / 100) + (subtotal * acrescimo_pct / 100)

    def _ao_alterar_acrescimo(self, evento=None) -> None:
        _, acrescimo_pct = self._percentuais_desconto_acrescimo()
        if acrescimo_pct > 0:
            self.frame_justificativa_acrescimo.pack(padx=15, pady=(6, 0), fill="x")
        else:
            self.frame_justificativa_acrescimo.pack_forget()
        self._atualizar_falta_pagar()

    def _total_pago(self) -> float:
        total = 0.0
        for registro in self.linhas_pagamento:
            texto_valor = (registro["entry"].get() or "0").strip().replace(",", ".")
            try:
                total += float(texto_valor)
            except ValueError:
                pass
        return total

    def _atualizar_falta_pagar(self) -> None:
        if not hasattr(self, "label_total"):
            return
        subtotal = self._subtotal_carrinho()
        desconto_pct, acrescimo_pct = self._percentuais_desconto_acrescimo()
        total = self._total_carrinho()
        pago = self._total_pago()
        falta = total - pago
        if desconto_pct or acrescimo_pct:
            partes = [f"Subtotal: {self.moeda} {subtotal:,.2f}"]
            if desconto_pct:
                partes.append(f"Desconto {desconto_pct:g}%: -{self.moeda} {subtotal * desconto_pct / 100:,.2f}")
            if acrescimo_pct:
                partes.append(f"Acréscimo {acrescimo_pct:g}%: +{self.moeda} {subtotal * acrescimo_pct / 100:,.2f}")
            self.label_subtotal.configure(text="  •  ".join(partes))
        else:
            self.label_subtotal.configure(text="")
        self.label_total.configure(text=f"{self.moeda} {total:,.2f}")
        if falta > 0.004:
            self.label_falta.configure(text=f"Falta pagar: {self.moeda} {falta:,.2f}")
        else:
            self.label_falta.configure(text="")

    def _coletar_pagamentos(self) -> list[dict]:
        pagamentos = []
        for registro in self.linhas_pagamento:
            texto_valor = (registro["entry"].get() or "0").strip().replace(",", ".")
            valor = float(texto_valor) if texto_valor else 0.0
            if valor > 0:
                pagamentos.append({"forma_pagamento": registro["combo"].get(), "valor": valor})
        if not pagamentos:
            raise ValidationError("Informe o valor de ao menos uma forma de pagamento.")
        return pagamentos

    def _adicionar_por_codigo(self) -> None:
        termo = self.entry_codigo.get().strip()
        if not termo:
            return
        produto = ProdutoController.buscar_por_codigo(termo)
        if not produto:
            candidatos = ProdutoController.listar(termo=termo)
            if len(candidatos) == 1:
                produto = candidatos[0]
            elif len(candidatos) > 1:
                messagebox.showinfo("Vários resultados", "Refine a busca: mais de um produto encontrado.")
                return
        if not produto:
            messagebox.showwarning("Não encontrado", "Nenhum produto localizado com esse código/nome.")
            return

        self._adicionar_produto_ao_carrinho(produto)
        self.entry_codigo.delete(0, "end")
        self._ocultar_sugestoes()

    def _adicionar_produto_ao_carrinho(self, produto) -> None:
        item_existente = next((i for i in self.carrinho if i["produto"].id == produto.id), None)
        if item_existente:
            item_existente["quantidade"] += 1
        else:
            self.carrinho.append({"produto": produto, "quantidade": 1})
        self._atualizar_carrinho()

    def _ao_digitar_busca(self, evento) -> None:
        if evento.keysym == "Return":
            return
        self._mostrar_sugestoes(self.entry_codigo.get())

    def _mostrar_sugestoes(self, termo: str) -> None:
        """Mostra os produtos que batem com o que já foi digitado; com o campo
        vazio (ex.: ao clicar), mostra todos os produtos do mercado."""
        produtos = ProdutoController.listar(termo=termo.strip())[:30]
        for w in self.frame_sugestoes.winfo_children():
            w.destroy()
        if not produtos:
            self.frame_sugestoes.pack_forget()
            return
        for produto in produtos:
            unidade = produto.unidade_medida or "un"
            texto = f"{produto.nome}  —  {self.moeda} {produto.preco_venda:.2f}/{unidade}"
            ctk.CTkButton(
                self.frame_sugestoes, text=texto, anchor="w", fg_color="transparent",
                hover_color=("gray85", "gray25"), text_color=("gray15", "gray90"),
                command=lambda p=produto: self._selecionar_sugestao(p),
            ).pack(fill="x", padx=4, pady=1)
        self.frame_sugestoes.pack(fill="x", pady=(6, 0))

    def _selecionar_sugestao(self, produto) -> None:
        self._adicionar_produto_ao_carrinho(produto)
        self.entry_codigo.delete(0, "end")
        self._ocultar_sugestoes()
        self.entry_codigo.focus_set()

    def _ocultar_sugestoes(self) -> None:
        self.frame_sugestoes.pack_forget()

    def _atualizar_carrinho(self) -> None:
        for w in self.carrinho_frame.winfo_children():
            w.destroy()

        total = 0.0
        for item in self.carrinho:
            produto, qtd = item["produto"], item["quantidade"]
            subtotal = produto.preco_venda * qtd
            total += subtotal

            linha = ctk.CTkFrame(self.carrinho_frame, corner_radius=8)
            linha.pack(fill="x", pady=3)
            unidade = produto.unidade_medida or "un"
            nome_qtd = f"{produto.nome}  ({self.moeda} {produto.preco_venda:.2f}/{unidade})"
            ctk.CTkLabel(linha, text=nome_qtd, width=260, anchor="w").pack(side="left", padx=8, pady=8)
            ctk.CTkButton(linha, text="-", width=28, command=lambda i=item: self._alterar_qtd(i, -1)).pack(side="left")

            entry_qtd = ctk.CTkEntry(linha, width=60, justify="center")
            entry_qtd.insert(0, f"{qtd:g}")
            entry_qtd.pack(side="left", padx=4)
            entry_qtd.bind("<Return>", lambda e, i=item, ent=entry_qtd: self._definir_qtd(i, ent))
            entry_qtd.bind("<FocusOut>", lambda e, i=item, ent=entry_qtd: self._definir_qtd(i, ent))

            ctk.CTkLabel(linha, text=unidade, width=30).pack(side="left")
            ctk.CTkButton(linha, text="+", width=28, command=lambda i=item: self._alterar_qtd(i, 1)).pack(side="left")
            ctk.CTkLabel(linha, text=f"{self.moeda} {subtotal:.2f}", width=100).pack(side="left", padx=8)
            ctk.CTkButton(
                linha, text="🗑️", width=30, fg_color="transparent", hover_color="#E74C3C",
                command=lambda i=item: self._remover_item(i)
            ).pack(side="right", padx=5)

        self._preencher_valor_pagamento_unico(self._total_carrinho())

    def _definir_qtd(self, item, entry) -> None:
        try:
            valor = float((entry.get() or "0").replace(",", "."))
            if valor <= 0:
                valor = item["quantidade"]
        except ValueError:
            valor = item["quantidade"]
        item["quantidade"] = ajustar_quantidade_para_unidade(valor, item["produto"].unidade_medida)
        self._atualizar_carrinho()

    def _alterar_qtd(self, item, delta) -> None:
        item["quantidade"] = max(1, item["quantidade"] + delta)
        self._atualizar_carrinho()

    def _remover_item(self, item) -> None:
        self.carrinho.remove(item)
        self._atualizar_carrinho()

    def _limpar_carrinho(self) -> None:
        self.carrinho = []
        self._resetar_desconto_acrescimo()
        self._atualizar_carrinho()

    def _resetar_desconto_acrescimo(self) -> None:
        self.entry_desconto.delete(0, "end")
        self.entry_acrescimo.delete(0, "end")
        self.entry_justificativa_acrescimo.delete(0, "end")
        self.frame_justificativa_acrescimo.pack_forget()

    def _finalizar_venda(self) -> None:
        if not self.carrinho:
            messagebox.showwarning("Atenção", "Adicione ao menos um produto à venda.")
            return

        try:
            pagamentos = self._coletar_pagamentos()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
            return

        itens = [{"produto_id": i["produto"].id, "quantidade": i["quantidade"]} for i in self.carrinho]
        try:
            venda = self._registrar(itens, pagamentos, confirmar=False)
        except ValidationError as e:
            if "Deseja continuar" in str(e):
                if not messagebox.askyesno("Estoque insuficiente", str(e)):
                    return
                try:
                    venda = self._registrar(itens, pagamentos, confirmar=True)
                except ValidationError as e2:
                    messagebox.showwarning("Atenção", str(e2))
                    return
            else:
                messagebox.showwarning("Atenção", str(e))
                return
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")
            return

        self.carrinho = []
        self.venda_aberta_id = None
        self.label_venda_aberta.configure(text="")
        self._resetar_desconto_acrescimo()
        self._atualizar_carrinho()
        self._atualizar_resumo_caixa()
        self._mostrar_pos_venda(venda)

    def _registrar(self, itens, pagamentos, confirmar):
        desconto_pct, acrescimo_pct = self._percentuais_desconto_acrescimo()
        justificativa = self.entry_justificativa_acrescimo.get().strip()
        if self.venda_aberta_id:
            VendaController.salvar_aberta(
                itens, self.usuario.id, self.usuario.login,
                cliente=self.entry_cliente.get(), venda_id=self.venda_aberta_id,
            )
            return VendaController.fechar_venda(
                self.venda_aberta_id, pagamentos, self.usuario.login,
                confirmar_estoque_insuficiente=confirmar,
                desconto_percentual=desconto_pct, acrescimo_percentual=acrescimo_pct,
                justificativa_acrescimo=justificativa,
            )
        return VendaController.registrar_venda(
            itens, pagamentos, self.usuario.id, self.usuario.login,
            cliente=self.entry_cliente.get(), confirmar_estoque_insuficiente=confirmar,
            desconto_percentual=desconto_pct, acrescimo_percentual=acrescimo_pct,
            justificativa_acrescimo=justificativa,
        )

    def _deixar_em_aberto(self) -> None:
        if not self.carrinho:
            messagebox.showwarning("Atenção", "Adicione ao menos um produto para deixar a venda em aberto.")
            return
        itens = [{"produto_id": i["produto"].id, "quantidade": i["quantidade"]} for i in self.carrinho]
        try:
            venda = VendaController.salvar_aberta(
                itens, self.usuario.id, self.usuario.login,
                cliente=self.entry_cliente.get(), venda_id=self.venda_aberta_id,
            )
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
            return
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")
            return

        messagebox.showinfo(
            "Venda em aberto",
            f"Venda nº {venda.numero_venda} deixada em aberto.\n"
            "Continue depois em Histórico de Vendas, sem travar a fila.",
        )
        self.carrinho = []
        self.venda_aberta_id = None
        self.entry_cliente.delete(0, "end")
        self._limpar_linhas_pagamento()
        self._resetar_desconto_acrescimo()
        self._atualizar_carrinho()
        self.label_venda_aberta.configure(text="")

    def carregar_venda_aberta(self, venda, ir_direto_ao_pagamento: bool = False) -> None:
        """Carrega uma venda em aberto no carrinho para continuar de onde parou."""
        self.venda_aberta_id = venda.id
        self.carrinho = [{"produto": item.produto, "quantidade": item.quantidade} for item in venda.itens]
        self.entry_cliente.delete(0, "end")
        if venda.cliente:
            self.entry_cliente.insert(0, venda.cliente)
        self._resetar_desconto_acrescimo()
        self.frame_pos_venda.pack_forget()
        self.frame_form.pack(fill="both", expand=True)
        self._atualizar_carrinho()
        self.label_venda_aberta.configure(text=f"⏸️ Continuando venda em aberto nº {venda.numero_venda}")
        if ir_direto_ao_pagamento:
            self._preencher_valor_pagamento_unico(self._total_carrinho())

    def _abrir_saida(self) -> None:
        FormularioSaidaCaixa(self, self.usuario, self._atualizar_resumo_caixa)

    def _atualizar_resumo_caixa(self) -> None:
        saldo = CaixaController.saldo_do_dia()
        cor = "#2ECC71" if saldo >= 0 else "#E74C3C"
        self.label_saldo.configure(text=f"Saldo do caixa hoje: {self.moeda} {saldo:,.2f}", text_color=cor)

    def _mostrar_pos_venda(self, venda) -> None:
        """
        Tela pós-pagamento: o recibo é opcional (o usuário decide se quer
        imprimir/exportar); "Nova Venda" já deixa o caixa pronto para o
        próximo cliente sem passar pelo recibo.
        """
        self.venda_concluida = venda
        self.frame_form.pack_forget()

        for w in self.frame_pos_venda.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self.frame_pos_venda, text="Venda concluída ✅", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(30, 5))
        ctk.CTkLabel(self.frame_pos_venda, text=f"Venda nº {venda.numero_venda}").pack()
        ctk.CTkLabel(
            self.frame_pos_venda, text=f"{self.moeda} {venda.valor_total:,.2f}",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(pady=(10, 30))

        ctk.CTkButton(
            self.frame_pos_venda, text="🖨️ Imprimir Recibo", height=45,
            command=lambda: self._abrir_recibo(venda),
        ).pack(padx=15, pady=8, fill="x")
        ctk.CTkButton(
            self.frame_pos_venda, text="🆕 Nova Venda", height=45, fg_color="#2ECC71", hover_color="#27AE60",
            command=self._nova_venda,
        ).pack(padx=15, pady=8, fill="x")

        self.frame_pos_venda.pack(fill="both", expand=True)

    def _nova_venda(self) -> None:
        self.frame_pos_venda.pack_forget()
        self.venda_aberta_id = None
        self.label_venda_aberta.configure(text="")
        self.entry_cliente.delete(0, "end")
        self._limpar_linhas_pagamento()
        self._resetar_desconto_acrescimo()
        self._atualizar_falta_pagar()
        self.frame_form.pack(fill="both", expand=True)

    def _abrir_recibo(self, venda) -> None:
        JanelaRecibo(self, venda, self.usuario)


class FormularioSaidaCaixa(ctk.CTkToplevel):
    """Registro de saída manual de caixa, sempre vinculada ao usuário logado."""

    def __init__(self, master, usuario, ao_salvar):
        super().__init__(master)
        self.usuario = usuario
        self.ao_salvar = ao_salvar
        self.title("Saída de Caixa")
        self.geometry("380x420")
        self.grab_set()

        ctk.CTkLabel(self, text="Saída de Caixa", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 15))
        self.entry_valor = ctk.CTkEntry(self, placeholder_text="Valor", width=300)
        self.entry_valor.pack(pady=8)
        self.entry_justificativa = ctk.CTkTextbox(self, width=300, height=90)
        self.entry_justificativa.pack(pady=8)
        self.entry_categoria = ctk.CTkEntry(self, placeholder_text="Categoria (opcional)", width=300)
        self.entry_categoria.pack(pady=8)
        self.entry_obs = ctk.CTkEntry(self, placeholder_text="Observações (opcional)", width=300)
        self.entry_obs.pack(pady=8)
        ctk.CTkButton(self, text="Registrar Saída", width=300, command=self._salvar).pack(pady=20)

    def _salvar(self) -> None:
        try:
            valor = float((self.entry_valor.get() or "0").replace(",", "."))
            CaixaController.registrar_saida(
                self.usuario.id, valor, self.entry_justificativa.get("1.0", "end").strip(),
                self.entry_categoria.get(), self.entry_obs.get(), self.usuario.login,
            )
            self.ao_salvar()
            self.destroy()
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Verifique o valor informado.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")


class JanelaRecibo(ctk.CTkToplevel):
    """Recibo pós-venda: exportar PDF, imprimir ou enviar por WhatsApp."""

    def __init__(self, master, venda, usuario):
        super().__init__(master)
        self.venda = venda
        self.usuario = usuario
        self.empresa = usuario.empresa
        self.nome_empresa = usuario.empresa.nome_fantasia or usuario.empresa.razao_social or usuario.empresa.nome \
            if usuario.empresa else ""
        self.title(f"Recibo - Venda nº {venda.numero_venda}")
        self.geometry("380x480")
        self.grab_set()

        moeda = ConfigController.obter("moeda")
        ctk.CTkLabel(self, text="Venda concluída ✅", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 10))
        caixa_texto = ctk.CTkTextbox(self, width=330, height=280)
        caixa_texto.pack(pady=5)
        caixa_texto.insert("1.0", ReciboController.texto_recibo(venda, self.nome_empresa, self.empresa))
        caixa_texto.configure(state="disabled")

        ctk.CTkLabel(self, text=f"Total: {moeda} {venda.valor_total:,.2f}", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)

        botoes = ctk.CTkFrame(self, fg_color="transparent")
        botoes.pack(pady=15)
        ctk.CTkButton(botoes, text="🖨️ Imprimir Recibo", width=200, command=self._imprimir_recibo).pack(pady=5)
        ctk.CTkButton(botoes, text="📄 Exportar / Abrir PDF", width=200, command=self._exportar_pdf).pack(pady=5)
        ctk.CTkButton(botoes, text="📱 Enviar por WhatsApp", width=200, command=self._enviar_whatsapp).pack(pady=5)
        ctk.CTkButton(botoes, text="Fechar", width=200, fg_color="transparent", border_width=1,
                      command=self.destroy).pack(pady=5)

    def _imprimir_recibo(self) -> None:
        try:
            caminho = ReciboController.gerar_pdf(self.venda, self.nome_empresa, self.empresa)
            if self._imprimir_arquivo(caminho):
                messagebox.showinfo("Imprimindo", "Recibo enviado para a impressora padrão.")
            else:
                self._abrir_arquivo(caminho)
                messagebox.showwarning(
                    "Atenção",
                    "Não há um leitor de PDF associado para impressão automática.\n\n"
                    "O recibo foi salvo e aberto para impressão manual (Ctrl+P).",
                )
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível imprimir o recibo: {e}")

    @staticmethod
    def _imprimir_arquivo(caminho: str) -> bool:
        impressora = (ConfigController.obter("impressora_recibo") or "").strip() or None
        if imprimir_pdf_direto(caminho, impressora):
            return True
        try:
            if sys.platform.startswith("win"):
                os.startfile(caminho, "print")  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["lp", caminho], check=True)
            else:
                subprocess.run(["lp", caminho], check=True)
            return True
        except OSError:
            return False

    def _exportar_pdf(self) -> None:
        try:
            caminho = ReciboController.gerar_pdf(self.venda, self.nome_empresa, self.empresa)
            self._abrir_arquivo(caminho)
            messagebox.showinfo("Recibo gerado", f"PDF salvo em:\n{caminho}")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível gerar o PDF: {e}")

    @staticmethod
    def _abrir_arquivo(caminho: str) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(caminho)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", caminho], check=False)
            else:
                subprocess.run(["xdg-open", caminho], check=False)
        except Exception:
            pass  # abrir automaticamente é apenas uma conveniência

    def _enviar_whatsapp(self) -> None:
        telefone = simpledialog.askstring("WhatsApp", "Telefone do cliente (com DDD):", parent=self)
        if not telefone:
            return
        try:
            ReciboController.enviar_whatsapp(self.venda, telefone, self.nome_empresa, self.empresa)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

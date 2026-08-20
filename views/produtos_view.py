"""
views/produtos_view.py
Cadastro de produtos, ficha técnica (produtos compostos) e embalagens.
Itens 1, 6, 7, 8, 9 e 10 da especificação.
"""
import os
import subprocess
import sys

import customtkinter as ctk
from tkinter import messagebox, simpledialog

from controllers.produto_controller import ProdutoController
from controllers.estoque_controller import EstoqueController
from controllers.etiqueta_controller import EtiquetaController
from controllers.config_controller import ConfigController
from utils.validators import ValidationError, ajustar_quantidade_para_unidade
from utils.impressora import imprimir_pdf_direto

UNIDADES_MEDIDA = ["un", "kg", "g", "L", "ml", "cx", "pct", "dz", "m"]


class ProdutosView(ctk.CTkFrame):
    """Listagem, pesquisa e CRUD de produtos."""

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self.moeda = ConfigController.obter("moeda")
        self._construir_layout()
        self._atualizar_lista()

    def _construir_layout(self) -> None:
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=30, pady=(25, 10))
        ctk.CTkLabel(topo, text="Produtos", font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        ctk.CTkButton(topo, text="+ Novo Produto", command=lambda: self._abrir_formulario()).pack(side="right")

        filtros = ctk.CTkFrame(self, fg_color="transparent")
        filtros.pack(fill="x", padx=30, pady=(0, 10))
        self.entry_pesquisa = ctk.CTkEntry(
            filtros, placeholder_text="Buscar por nome, código de barras, SKU ou código interno...", width=420
        )
        self.entry_pesquisa.pack(side="left")
        self.entry_pesquisa.bind("<KeyRelease>", lambda e: self._atualizar_lista())

        self.lista_frame = ctk.CTkScrollableFrame(self)
        self.lista_frame.pack(fill="both", expand=True, padx=30, pady=(0, 25))

    def _atualizar_lista(self) -> None:
        for widget in self.lista_frame.winfo_children():
            widget.destroy()

        termo = self.entry_pesquisa.get().strip()
        produto_exato = ProdutoController.buscar_por_codigo(termo) if termo and termo.isdigit() and len(termo) < 6 else None
        produtos = [produto_exato] if produto_exato else ProdutoController.listar(termo=termo)

        if not produtos:
            ctk.CTkLabel(self.lista_frame, text="Nenhum produto encontrado.").pack(pady=20)
            return

        cab = ctk.CTkFrame(self.lista_frame, fg_color="transparent")
        cab.pack(fill="x", pady=(0, 5))
        for texto, largura in [("Cód.", 50), ("Nome", 220), ("Categoria", 130),
                                ("Estoque (venda+prat.)", 150), ("Custo", 90), ("Venda", 90)]:
            ctk.CTkLabel(cab, text=texto, width=largura, font=ctk.CTkFont(weight="bold")).pack(side="left")

        for produto in produtos:
            estoque_total = produto.estoque_venda + produto.estoque_prateleira
            cor = "#E74C3C" if estoque_total < 0 else (
                "#E67E22" if produto.estoque_minimo and estoque_total <= produto.estoque_minimo else None
            )
            linha = ctk.CTkFrame(self.lista_frame, corner_radius=8)
            linha.pack(fill="x", pady=3)
            ctk.CTkLabel(linha, text=str(produto.codigo_interno), width=50).pack(side="left", padx=5, pady=8)
            nome = produto.nome + (" (composto)" if produto.composto else "")
            ctk.CTkLabel(linha, text=nome, width=220, anchor="w").pack(side="left", pady=8)
            ctk.CTkLabel(linha, text=produto.categoria or "-", width=130).pack(side="left", pady=8)
            ctk.CTkLabel(linha, text=f"{estoque_total:g} {produto.unidade_medida}", width=150,
                         text_color=cor).pack(side="left", pady=8)
            ctk.CTkLabel(linha, text=f"{self.moeda} {produto.preco_custo:.2f}", width=90).pack(side="left", pady=8)
            ctk.CTkLabel(linha, text=f"{self.moeda} {produto.preco_venda:.2f}", width=90).pack(side="left", pady=8)
            ctk.CTkButton(
                linha, text="🗑️", width=35, fg_color="transparent", hover_color="#E74C3C",
                command=lambda p=produto: self._inativar(p)
            ).pack(side="right", padx=3)
            ctk.CTkButton(
                linha, text="✏️", width=35, fg_color="transparent",
                command=lambda p=produto: self._abrir_formulario(p)
            ).pack(side="right", padx=3)
            ctk.CTkButton(
                linha, text="📥 Estoque", width=90, fg_color="#2ECC71", hover_color="#27AE60",
                command=lambda p=produto: self._adicionar_estoque(p)
            ).pack(side="right", padx=3)
            ctk.CTkButton(
                linha, text="🏷️ Etiqueta", width=90, fg_color="#3498DB", hover_color="#2980B9",
                command=lambda p=produto: self._imprimir_etiqueta(p)
            ).pack(side="right", padx=3)

    def _imprimir_etiqueta(self, produto) -> None:
        copias = simpledialog.askinteger(
            "Imprimir Etiqueta", f"Quantas etiquetas de '{produto.nome}' deseja imprimir?",
            parent=self, minvalue=1, initialvalue=1,
        )
        if not copias:
            return
        try:
            caminho = EtiquetaController.gerar_pdf(produto, copias=copias)
            resposta = messagebox.askyesnocancel(
                "Etiqueta gerada",
                "Etiqueta gerada com sucesso.\n\nSim = Imprimir agora\nNão = Apenas abrir o PDF",
            )
            if resposta is None:
                return
            if resposta:
                if not self._imprimir_arquivo(caminho):
                    self._abrir_arquivo(caminho)
                    messagebox.showwarning(
                        "Atenção",
                        "Não há um leitor de PDF associado para impressão automática.\n\n"
                        "A etiqueta foi salva e aberta para impressão manual (Ctrl+P).",
                    )
            else:
                self._abrir_arquivo(caminho)
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Quantidade inválida.")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível gerar a etiqueta: {e}")

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
            pass

    @staticmethod
    def _imprimir_arquivo(caminho: str) -> bool:
        impressora = (ConfigController.obter("impressora_etiqueta") or "").strip() or None
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
            self._atualizar_lista()
            messagebox.showinfo("Sucesso", f"+{qtd:g} {produto.unidade_medida} adicionados ao estoque de {produto.nome}.")
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Quantidade inválida.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    def _inativar(self, produto) -> None:
        if messagebox.askyesno("Confirmar", f"Inativar o produto '{produto.nome}'?"):
            ProdutoController.inativar(produto.id, self.usuario.login)
            self._atualizar_lista()

    def _abrir_formulario(self, produto=None) -> None:
        FormularioProduto(self, produto, self.usuario, self._atualizar_lista)


class FormularioProduto(ctk.CTkToplevel):
    """Cadastro/edição de produto com abas de dados gerais, ficha técnica e embalagens."""

    def __init__(self, master, produto, usuario, ao_salvar):
        super().__init__(master)
        self.produto = produto
        self.usuario = usuario
        self.ao_salvar = ao_salvar

        self.title("Editar Produto" if produto else "Novo Produto")
        self.geometry("560x640")
        self.grab_set()
        self._construir_layout()

    def _construir_layout(self) -> None:
        abas = ctk.CTkTabview(self, width=520, height=600)
        abas.pack(padx=15, pady=15, fill="both", expand=True)
        aba_geral = abas.add("Dados Gerais")
        aba_ficha = abas.add("Ficha Técnica")
        aba_embalagem = abas.add("Embalagens")

        self._construir_aba_geral(aba_geral)
        self._construir_aba_ficha(aba_ficha)
        self._construir_aba_embalagem(aba_embalagem)

    # --- Dados gerais ---
    def _construir_aba_geral(self, aba) -> None:
        self.entry_nome = ctk.CTkEntry(aba, placeholder_text="Nome do produto", width=460)
        self.entry_nome.pack(pady=6)
        self.entry_categoria = ctk.CTkEntry(aba, placeholder_text="Categoria", width=460)
        self.entry_categoria.pack(pady=6)

        linha_cod = ctk.CTkFrame(aba, fg_color="transparent")
        linha_cod.pack(pady=6)
        self.entry_codigo_barras = ctk.CTkEntry(linha_cod, placeholder_text="Código de barras (opcional)", width=225)
        self.entry_codigo_barras.pack(side="left", padx=(0, 10))
        self.entry_codigo_sku = ctk.CTkEntry(linha_cod, placeholder_text="Código/SKU (opcional)", width=225)
        self.entry_codigo_sku.pack(side="left")

        self.combo_unidade = ctk.CTkComboBox(aba, values=UNIDADES_MEDIDA, width=460)
        self.combo_unidade.pack(pady=6)

        linha_precos = ctk.CTkFrame(aba, fg_color="transparent")
        linha_precos.pack(pady=6)
        self.entry_custo = ctk.CTkEntry(linha_precos, placeholder_text="Preço de custo", width=150)
        self.entry_custo.pack(side="left", padx=(0, 10))
        self.entry_venda = ctk.CTkEntry(linha_precos, placeholder_text="Preço de venda", width=150)
        self.entry_venda.pack(side="left", padx=(0, 10))
        self.entry_margem = ctk.CTkEntry(linha_precos, placeholder_text="Margem % (opcional)", width=150)
        self.entry_margem.pack(side="left")

        linha_estoque = ctk.CTkFrame(aba, fg_color="transparent")
        linha_estoque.pack(pady=6)
        placeholder_estoque = "Estoque atual (não editável aqui)" if self.produto else "Estoque inicial (venda)"
        self.entry_estoque = ctk.CTkEntry(linha_estoque, placeholder_text=placeholder_estoque, width=225)
        self.entry_estoque.pack(side="left", padx=(0, 10))
        self.entry_estoque_min = ctk.CTkEntry(linha_estoque, placeholder_text="Estoque mínimo (alerta)", width=225)
        self.entry_estoque_min.pack(side="left")

        if self.produto:
            ctk.CTkButton(
                aba, text="📥 Adicionar Entrada de Estoque", width=460, fg_color="#2ECC71",
                hover_color="#27AE60", command=self._adicionar_estoque,
            ).pack(pady=(0, 6))

        self.check_composto_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            aba, text="Produto composto (produzido via ficha técnica)", variable=self.check_composto_var
        ).pack(pady=10)

        if self.produto:
            self.entry_nome.insert(0, self.produto.nome)
            self.entry_categoria.insert(0, self.produto.categoria or "")
            self.entry_codigo_barras.insert(0, self.produto.codigo_barras or "")
            self.entry_codigo_sku.insert(0, self.produto.codigo_sku or "")
            self.combo_unidade.set(self.produto.unidade_medida if self.produto.unidade_medida in UNIDADES_MEDIDA else UNIDADES_MEDIDA[0])
            self.entry_custo.insert(0, str(self.produto.preco_custo))
            self.entry_venda.insert(0, str(self.produto.preco_venda))
            self.entry_estoque.insert(0, str(self.produto.estoque_venda))
            self.entry_estoque.configure(state="disabled")
            self.entry_estoque_min.insert(0, str(self.produto.estoque_minimo))
            self.check_composto_var.set(self.produto.composto)
        else:
            self.combo_unidade.set("un")
            self.entry_estoque.insert(0, "0")
            self.entry_estoque_min.insert(0, "0")

        ctk.CTkButton(aba, text="Salvar Produto", width=460, command=self._salvar).pack(pady=15)

    def _salvar(self) -> None:
        try:
            preco_custo = float((self.entry_custo.get() or "0").replace(",", "."))
            preco_venda = float((self.entry_venda.get() or "0").replace(",", "."))
            if self.entry_margem.get().strip():
                margem = float(self.entry_margem.get().replace(",", "."))
                preco_venda = round(preco_custo * (1 + margem / 100), 2)

            if self.produto:
                ProdutoController.editar(
                    self.produto.id, usuario=self.usuario.login,
                    nome=self.entry_nome.get(), categoria=self.entry_categoria.get(),
                    codigo_barras=self.entry_codigo_barras.get(), codigo_sku=self.entry_codigo_sku.get(),
                    unidade_medida=self.combo_unidade.get(), preco_custo=preco_custo, preco_venda=preco_venda,
                    estoque_minimo=float(self.entry_estoque_min.get() or 0),
                )
            else:
                ProdutoController.criar(
                    nome=self.entry_nome.get(), categoria=self.entry_categoria.get(),
                    codigo_barras=self.entry_codigo_barras.get(), codigo_sku=self.entry_codigo_sku.get(),
                    unidade_medida=self.combo_unidade.get(), preco_custo=preco_custo, preco_venda=preco_venda,
                    estoque_venda=float(self.entry_estoque.get() or 0),
                    estoque_minimo=float(self.entry_estoque_min.get() or 0),
                    composto=self.check_composto_var.get(), usuario=self.usuario.login,
                    empresa_id=self.usuario.empresa_id,
                )
            self.ao_salvar()
            self.destroy()
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Verifique os valores numéricos informados.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    def _adicionar_estoque(self) -> None:
        from tkinter import simpledialog
        qtd = simpledialog.askfloat(
            "Entrada de Estoque", f"Quantidade de '{self.produto.nome}' a adicionar ({self.produto.unidade_medida}):",
            parent=self, minvalue=0.001,
        )
        if not qtd:
            return
        qtd = ajustar_quantidade_para_unidade(qtd, self.produto.unidade_medida)
        try:
            EstoqueController.entrada(
                self.produto.id, qtd, motivo="Entrada manual de estoque",
                usuario_id=self.usuario.id, usuario=self.usuario.login,
            )
            self.produto = ProdutoController.obter(self.produto.id)
            self.entry_estoque.configure(state="normal")
            self.entry_estoque.delete(0, "end")
            self.entry_estoque.insert(0, str(self.produto.estoque_venda))
            self.entry_estoque.configure(state="disabled")
            self.ao_salvar()
            messagebox.showinfo("Sucesso", f"+{qtd:g} {self.produto.unidade_medida} adicionados ao estoque.")
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Quantidade inválida.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    # --- Ficha técnica ---
    def _construir_aba_ficha(self, aba) -> None:
        if not self.produto:
            ctk.CTkLabel(
                aba, text="Salve o produto primeiro para cadastrar a ficha técnica.", wraplength=450
            ).pack(pady=30)
            return

        ctk.CTkLabel(aba, text="Ingredientes (produtos já cadastrados):", anchor="w").pack(fill="x", pady=(10, 5))
        self.frame_ingredientes = ctk.CTkScrollableFrame(aba, width=480, height=380)
        self.frame_ingredientes.pack(pady=5, fill="both", expand=True)

        self.produtos_disponiveis = [
            p for p in ProdutoController.listar() if p.id != self.produto.id
        ]
        existentes = ProdutoController.obter_ficha_tecnica(self.produto.id)
        if existentes:
            for item in existentes:
                self._linha_ingrediente(item.ingrediente_id, item.quantidade, item.unidade_medida)
        else:
            self._linha_ingrediente()

        botoes = ctk.CTkFrame(aba, fg_color="transparent")
        botoes.pack(pady=10)
        ctk.CTkButton(botoes, text="+ Ingrediente", width=150, command=lambda: self._linha_ingrediente()).pack(side="left", padx=5)
        ctk.CTkButton(botoes, text="Salvar Ficha Técnica", width=200, command=self._salvar_ficha).pack(side="left", padx=5)

    def _linha_ingrediente(self, ingrediente_id=None, quantidade=None, unidade="un") -> None:
        linha = ctk.CTkFrame(self.frame_ingredientes)
        linha.pack(fill="x", pady=3)
        nomes = [p.nome for p in self.produtos_disponiveis]
        combo = ctk.CTkComboBox(linha, values=nomes, width=220)
        if ingrediente_id:
            nome_ing = next((p.nome for p in self.produtos_disponiveis if p.id == ingrediente_id), "")
            combo.set(nome_ing)
        elif nomes:
            combo.set(nomes[0])
        combo.pack(side="left", padx=5, pady=5)
        entry_qtd = ctk.CTkEntry(linha, placeholder_text="Quantidade", width=100)
        if quantidade is not None:
            entry_qtd.insert(0, str(quantidade))
        entry_qtd.pack(side="left", padx=5)
        entry_un = ctk.CTkEntry(linha, placeholder_text="Unidade", width=70)
        entry_un.insert(0, unidade)
        entry_un.pack(side="left", padx=5)
        ctk.CTkButton(
            linha, text="🗑️", width=30, fg_color="transparent", hover_color="#E74C3C",
            command=lambda: linha.destroy()
        ).pack(side="left", padx=5)
        linha.combo = combo
        linha.entry_qtd = entry_qtd
        linha.entry_un = entry_un

    def _salvar_ficha(self) -> None:
        try:
            ingredientes = []
            for linha in self.frame_ingredientes.winfo_children():
                nome = linha.combo.get()
                produto_ing = next((p for p in self.produtos_disponiveis if p.nome == nome), None)
                if not produto_ing:
                    continue
                qtd = float((linha.entry_qtd.get() or "0").replace(",", "."))
                ingredientes.append({
                    "ingrediente_id": produto_ing.id, "quantidade": qtd,
                    "unidade_medida": linha.entry_un.get() or "un",
                })
            ProdutoController.definir_ficha_tecnica(self.produto.id, ingredientes, self.usuario.login)
            resumo = ProdutoController.resumo_custos(self.produto.id)
            messagebox.showinfo(
                "Ficha técnica salva",
                f"Custo total: {resumo['custo_total']:.2f}\nLucro bruto: {resumo['lucro_bruto']:.2f}\n"
                f"Margem: {resumo['percentual_lucro']:.1f}%",
            )
            self.ao_salvar()
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Verifique as quantidades informadas.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    # --- Embalagens ---
    def _construir_aba_embalagem(self, aba) -> None:
        if not self.produto:
            ctk.CTkLabel(
                aba, text="Salve o produto primeiro para cadastrar embalagens.", wraplength=450
            ).pack(pady=30)
            return

        ctk.CTkLabel(aba, text="Cadastrar caixa/embalagem:", anchor="w").pack(fill="x", pady=(10, 5))
        self.entry_cod_caixa = ctk.CTkEntry(aba, placeholder_text="Código da caixa", width=460)
        self.entry_cod_caixa.pack(pady=5)
        self.entry_qtd_caixa = ctk.CTkEntry(aba, placeholder_text="Quantidade de unidades por caixa", width=460)
        self.entry_qtd_caixa.pack(pady=5)
        self.entry_valor_caixa = ctk.CTkEntry(aba, placeholder_text="Valor da caixa", width=460)
        self.entry_valor_caixa.pack(pady=5)
        self.entry_cod_unidade = ctk.CTkEntry(aba, placeholder_text="Código da unidade", width=460)
        self.entry_cod_unidade.pack(pady=5)
        self.entry_valor_unidade = ctk.CTkEntry(aba, placeholder_text="Valor da unidade", width=460)
        self.entry_valor_unidade.pack(pady=5)
        ctk.CTkButton(aba, text="Adicionar Embalagem", width=460, command=self._salvar_embalagem).pack(pady=15)

        ctk.CTkLabel(aba, text="Embalagens cadastradas:", anchor="w").pack(fill="x", pady=(5, 5))
        self.lista_embalagens = ctk.CTkScrollableFrame(aba, width=460, height=150)
        self.lista_embalagens.pack(fill="both", expand=True)
        self._atualizar_embalagens()

    def _atualizar_embalagens(self) -> None:
        for w in self.lista_embalagens.winfo_children():
            w.destroy()
        for emb in self.produto.embalagens:
            texto = (
                f"{emb.codigo_caixa or '-'} ({emb.qtd_unidades_por_caixa:g} un/caixa) "
                f"- estoque: {emb.estoque_caixas:g} caixas / {emb.estoque_unidades:g} un"
            )
            ctk.CTkLabel(self.lista_embalagens, text=texto, anchor="w").pack(fill="x", pady=2)

    def _salvar_embalagem(self) -> None:
        try:
            ProdutoController.adicionar_embalagem(
                self.produto.id, self.entry_cod_caixa.get(),
                float((self.entry_qtd_caixa.get() or "1").replace(",", ".")),
                float((self.entry_valor_caixa.get() or "0").replace(",", ".")),
                self.entry_cod_unidade.get(),
                float((self.entry_valor_unidade.get() or "0").replace(",", ".")),
                self.usuario.login,
            )
            self.produto = ProdutoController.obter(self.produto.id)
            self._atualizar_embalagens()
            self.entry_cod_caixa.delete(0, "end")
            self.entry_qtd_caixa.delete(0, "end")
            self.entry_valor_caixa.delete(0, "end")
            self.entry_cod_unidade.delete(0, "end")
            self.entry_valor_unidade.delete(0, "end")
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Verifique os valores informados.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

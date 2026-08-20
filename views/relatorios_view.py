"""
views/relatorios_view.py
Tela de relatórios: aba "Resumo" (cards, gráficos e últimas
movimentações, antes na Dashboard) e aba "Exportar" (geração de
relatórios em PDF, Excel e CSV).
"""
from datetime import date, datetime, timedelta
from collections import defaultdict

import customtkinter as ctk
from tkinter import messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from controllers.relatorio_controller import RelatorioController
from controllers.receita_controller import ReceitaController
from controllers.despesa_controller import DespesaController
from controllers.config_controller import ConfigController
from controllers.produto_controller import ProdutoController
from controllers.estoque_controller import EstoqueController
from controllers.caixa_controller import CaixaController
from controllers.venda_controller import VendaController

PERIODOS_RESUMO = {
    "Diário": 1,
    "Semanal": 7,
    "Mensal": 30,
}


class RelatoriosView(ctk.CTkFrame):
    """Resumo financeiro/operacional e exportação de relatórios."""

    PERIODOS = {
        "Hoje": 0,
        "Últimos 7 dias": 7,
        "Últimos 30 dias": 30,
        "Este ano": 365,
    }

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self.moeda = ConfigController.obter("moeda")
        self.periodo_resumo = "Mensal"
        self._construir_layout()

    def _construir_layout(self) -> None:
        ctk.CTkLabel(
            self, text="Relatórios", font=ctk.CTkFont(size=26, weight="bold")
        ).pack(anchor="w", padx=30, pady=(25, 15))

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=30, pady=(0, 25))
        self.tabview.add("Resumo")
        self.tabview.add("Exportar")

        self._construir_aba_resumo(self.tabview.tab("Resumo"))
        self._construir_aba_exportar(self.tabview.tab("Exportar"))

    # ------------------------------------------------------------------
    # Aba Resumo (cards, gráficos, últimas movimentações)
    # ------------------------------------------------------------------
    def _construir_aba_resumo(self, master) -> None:
        filtro = ctk.CTkFrame(master, fg_color="transparent")
        filtro.pack(fill="x", pady=(5, 10))
        self.segmentado = ctk.CTkSegmentedButton(
            filtro, values=list(PERIODOS_RESUMO.keys()), command=self._trocar_periodo_resumo
        )
        self.segmentado.set(self.periodo_resumo)
        self.segmentado.pack(side="right")

        self.corpo_resumo = ctk.CTkScrollableFrame(master, fg_color="transparent")
        self.corpo_resumo.pack(fill="both", expand=True)
        self._atualizar_resumo()

    def _trocar_periodo_resumo(self, valor: str) -> None:
        self.periodo_resumo = valor
        self._atualizar_resumo()

    def _atualizar_resumo(self) -> None:
        for widget in self.corpo_resumo.winfo_children():
            widget.destroy()

        hoje = date.today()
        if self.periodo_resumo == "Diário":
            data_inicio = hoje
        elif self.periodo_resumo == "Semanal":
            data_inicio = hoje - timedelta(days=6)
        else:
            data_inicio = hoje.replace(day=1)

        receitas = ReceitaController.listar(data_inicio=data_inicio, data_fim=hoje)
        despesas = DespesaController.listar(data_inicio=data_inicio, data_fim=hoje)

        total_receitas = sum(r.valor for r in receitas)
        total_despesas = sum(d.valor for d in despesas)
        saldo = total_receitas - total_despesas
        economia = saldo if saldo > 0 else 0.0
        self._construir_corpo_resumo(
            receitas, despesas, total_receitas, total_despesas, saldo, economia, data_inicio, hoje
        )

    def _construir_corpo_resumo(self, receitas, despesas, total_receitas, total_despesas,
                                 saldo, economia, data_inicio, hoje) -> None:
        master = self.corpo_resumo

        cards_frame = ctk.CTkFrame(master, fg_color="transparent")
        cards_frame.pack(fill="x")
        for i in range(4):
            cards_frame.grid_columnconfigure(i, weight=1)

        self._criar_card(cards_frame, 0, "Saldo do Período", saldo, "#2ECC71" if saldo >= 0 else "#E74C3C")
        self._criar_card(cards_frame, 1, "Receitas do Período", total_receitas, "#3498DB")
        self._criar_card(cards_frame, 2, "Despesas do Período", total_despesas, "#E67E22")
        self._criar_card(cards_frame, 3, "Economia do Período", economia, "#9B59B6")

        self._construir_bloco_loja(master)

        graficos_frame = ctk.CTkFrame(master, fg_color="transparent")
        graficos_frame.pack(fill="both", expand=True, pady=20)
        graficos_frame.grid_columnconfigure((0, 1), weight=1)
        graficos_frame.grid_rowconfigure((0, 1), weight=1)

        self._grafico_linha_diaria(graficos_frame, receitas, despesas, data_inicio, hoje)
        self._grafico_por_categoria(graficos_frame, despesas)

        ctk.CTkLabel(
            master, text="Últimas Movimentações", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", pady=(10, 5))

        lista_frame = ctk.CTkFrame(master, fg_color="transparent")
        lista_frame.pack(fill="x", pady=(0, 25))

        movimentos = [("Receita", r.descricao, r.valor, r.data) for r in receitas]
        movimentos += [("Despesa", d.descricao, d.valor, d.data) for d in despesas]
        movimentos.sort(key=lambda m: m[3], reverse=True)

        if not movimentos:
            ctk.CTkLabel(lista_frame, text="Nenhuma movimentação neste período.").pack(pady=10)
        for tipo, descricao, valor, data_mov in movimentos[:10]:
            cor = "#2ECC71" if tipo == "Receita" else "#E74C3C"
            sinal = "+" if tipo == "Receita" else "-"
            linha = ctk.CTkFrame(lista_frame, fg_color="transparent")
            linha.pack(fill="x", pady=2)
            ctk.CTkLabel(linha, text=data_mov.strftime("%d/%m/%Y"), width=90).pack(side="left")
            ctk.CTkLabel(linha, text=descricao, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                linha, text=f"{sinal} {self.moeda} {valor:,.2f}", text_color=cor
            ).pack(side="right", padx=10)

    def _construir_bloco_loja(self, master) -> None:
        ctk.CTkLabel(
            master, text="Loja, Estoque e Caixa (hoje)", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", pady=(15, 5))

        produtos = ProdutoController.listar()
        estoque_total = sum(p.estoque_venda + p.estoque_prateleira for p in produtos)
        prateleira_total = sum(p.estoque_prateleira for p in produtos)
        estoque_baixo = EstoqueController.listar_estoque_baixo()
        estoque_negativo = EstoqueController.listar_estoque_negativo()
        valor_estoque = EstoqueController.valor_total_estoque()
        entradas = CaixaController.entradas_do_dia()
        saidas = CaixaController.saidas_do_dia()
        saldo_caixa = CaixaController.saldo_do_dia()

        cards = ctk.CTkFrame(master, fg_color="transparent")
        cards.pack(fill="x")
        for i in range(5):
            cards.grid_columnconfigure(i, weight=1)

        self._criar_card_texto(cards, 0, 0, "Produtos em Estoque", f"{estoque_total:g}", "#3498DB")
        self._criar_card_texto(cards, 0, 1, "Produtos na Prateleira", f"{prateleira_total:g}", "#3498DB")
        self._criar_card_texto(cards, 0, 2, "Estoque Baixo", str(len(estoque_baixo)), "#E67E22")
        self._criar_card_texto(cards, 0, 3, "Estoque Negativo", str(len(estoque_negativo)), "#E74C3C")
        self._criar_card(cards, 4, "Valor do Estoque", valor_estoque, "#9B59B6")

        cards2 = ctk.CTkFrame(master, fg_color="transparent")
        cards2.pack(fill="x", pady=(8, 0))
        for i in range(4):
            cards2.grid_columnconfigure(i, weight=1)
        self._criar_card(cards2, 0, "Vendas do Dia", entradas, "#2ECC71")
        self._criar_card(cards2, 1, "Entradas do Caixa", entradas, "#2ECC71")
        self._criar_card(cards2, 2, "Saídas do Caixa", saidas, "#E67E22")
        self._criar_card(cards2, 3, "Saldo do Caixa", saldo_caixa, "#2ECC71" if saldo_caixa >= 0 else "#E74C3C")

        mais_vendidos = VendaController.produtos_mais_vendidos(limite=5)
        if mais_vendidos:
            ctk.CTkLabel(
                master, text="Produtos mais vendidos", font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w", pady=(15, 5))
            texto = "  •  ".join(f"{m['nome']} ({m['quantidade']:g})" for m in mais_vendidos)
            ctk.CTkLabel(master, text=texto, anchor="w").pack(anchor="w")

    def _criar_card_texto(self, master, row: int, coluna: int, titulo: str, valor: str, cor: str) -> None:
        card = ctk.CTkFrame(master, corner_radius=12)
        card.grid(row=row, column=coluna, padx=8, pady=5, sticky="nsew")
        ctk.CTkLabel(card, text=titulo, text_color=("gray35", "gray70")).pack(padx=15, pady=(15, 2), anchor="w")
        ctk.CTkLabel(
            card, text=valor, font=ctk.CTkFont(size=20, weight="bold"), text_color=cor
        ).pack(padx=15, pady=(0, 15), anchor="w")

    def _criar_card(self, master, coluna: int, titulo: str, valor: float, cor: str) -> None:
        card = ctk.CTkFrame(master, corner_radius=12)
        card.grid(row=0, column=coluna, padx=8, pady=5, sticky="nsew")
        ctk.CTkLabel(card, text=titulo, text_color=("gray35", "gray70")).pack(padx=15, pady=(15, 2), anchor="w")
        ctk.CTkLabel(
            card, text=f"{self.moeda} {valor:,.2f}",
            font=ctk.CTkFont(size=20, weight="bold"), text_color=cor
        ).pack(padx=15, pady=(0, 15), anchor="w")

    def _grafico_linha_diaria(self, master, receitas, despesas, data_inicio, data_fim) -> None:
        fig = Figure(figsize=(4.5, 3.2), dpi=100)
        fig.patch.set_alpha(0)
        ax = fig.add_subplot(111)

        totais = defaultdict(lambda: [0.0, 0.0])
        for r in receitas:
            totais[r.data][0] += r.valor
        for d in despesas:
            totais[d.data][1] += d.valor

        dias = []
        atual = data_inicio
        while atual <= data_fim:
            dias.append(atual)
            atual += timedelta(days=1)

        valores_receita = [totais[d][0] for d in dias]
        valores_despesa = [totais[d][1] for d in dias]
        rotulos = [d.strftime("%d/%m") for d in dias]

        ax.plot(rotulos, valores_receita, marker="o", label="Receitas", color="#2ECC71")
        ax.plot(rotulos, valores_despesa, marker="o", label="Despesas", color="#E74C3C")
        if len(rotulos) > 10:
            passo = max(1, len(rotulos) // 10)
            ax.set_xticks(rotulos[::passo])
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.set_title("Receitas x Despesas (por dia)")
        ax.legend(fontsize=8)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=master)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=5)

    def _grafico_por_categoria(self, master, despesas) -> None:
        fig = Figure(figsize=(4.5, 3.2), dpi=100)
        fig.patch.set_alpha(0)
        ax = fig.add_subplot(111)

        totais_categoria = defaultdict(float)
        cores_categoria = {}
        for d in despesas:
            totais_categoria[d.categoria.nome] += d.valor
            cores_categoria[d.categoria.nome] = d.categoria.cor

        if totais_categoria:
            nomes = list(totais_categoria.keys())
            valores = list(totais_categoria.values())
            cores = [cores_categoria[n] for n in nomes]
            ax.pie(valores, labels=nomes, autopct="%1.0f%%", colors=cores,
                   textprops={"fontsize": 8})
        else:
            ax.text(0.5, 0.5, "Sem despesas no mês", ha="center", va="center")
            ax.axis("off")

        ax.set_title("Despesas por Categoria")
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=master)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=1, sticky="nsew", padx=5)

    # ------------------------------------------------------------------
    # Aba Exportar (formulário original de exportação)
    # ------------------------------------------------------------------
    def _construir_aba_exportar(self, master) -> None:
        card = ctk.CTkFrame(master, corner_radius=12)
        card.pack(pady=10, fill="x")

        ctk.CTkLabel(card, text="Período", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=25, pady=(20, 5)
        )
        self.combo_periodo = ctk.CTkComboBox(
            card, values=list(self.PERIODOS.keys()), width=300,
            dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"),
        )
        self.combo_periodo.set("Últimos 30 dias")
        self.combo_periodo.pack(anchor="w", padx=25, pady=(0, 15))

        ctk.CTkLabel(card, text="Agrupar por", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=25, pady=(0, 5)
        )
        self.combo_agrupamento = ctk.CTkComboBox(
            card, values=["dia", "semana", "mes", "ano", "categoria"], width=300,
            dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"),
        )
        self.combo_agrupamento.set("mes")
        self.combo_agrupamento.pack(anchor="w", padx=25, pady=(0, 15))

        ctk.CTkLabel(card, text="Pasta de destino", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=25, pady=(0, 5)
        )
        self.entry_pasta = ctk.CTkEntry(card, width=300)
        self.entry_pasta.insert(0, ConfigController.obter("pasta_exportacao"))
        self.entry_pasta.pack(anchor="w", padx=25, pady=(0, 20))

        botoes_frame = ctk.CTkFrame(card, fg_color="transparent")
        botoes_frame.pack(anchor="w", padx=25, pady=(0, 25))
        ctk.CTkButton(
            botoes_frame, text="📄 Exportar PDF", width=150,
            command=lambda: self._exportar("pdf")
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            botoes_frame, text="📊 Exportar Excel", width=150,
            command=lambda: self._exportar("excel")
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            botoes_frame, text="📑 Exportar CSV", width=150,
            command=lambda: self._exportar("csv")
        ).pack(side="left")
        ctk.CTkButton(
            botoes_frame, text="📈 Visualizar Gráfico", width=170,
            command=self._atualizar_grafico
        ).pack(side="left", padx=(10, 0))

        self.label_status = ctk.CTkLabel(master, text="", text_color=("gray35", "gray70"))
        self.label_status.pack(anchor="w")

        self.grafico_frame = ctk.CTkFrame(master, corner_radius=12)
        self.grafico_frame.pack(fill="both", expand=True, pady=(10, 15))
        self._atualizar_grafico()

    def _atualizar_grafico(self) -> None:
        for widget in self.grafico_frame.winfo_children():
            widget.destroy()

        data_inicio, data_fim = self._calcular_periodo()
        receitas = ReceitaController.listar(data_inicio=data_inicio, data_fim=data_fim)
        despesas = DespesaController.listar(data_inicio=data_inicio, data_fim=data_fim)

        totais = defaultdict(lambda: [0.0, 0.0])
        for r in receitas:
            totais[r.data][0] += r.valor
        for d in despesas:
            totais[d.data][1] += d.valor

        dias = []
        atual = data_inicio
        while atual <= data_fim:
            dias.append(atual)
            atual += timedelta(days=1)

        rotulos = [d.strftime("%d/%m") for d in dias]
        valores_receita = [totais[d][0] for d in dias]
        valores_despesa = [totais[d][1] for d in dias]

        fig = Figure(figsize=(9, 3.2), dpi=100)
        fig.patch.set_alpha(0)
        ax = fig.add_subplot(111)
        ax.plot(rotulos, valores_receita, marker="o", label="Arrecadação", color="#2ECC71")
        ax.plot(rotulos, valores_despesa, marker="o", label="Despesa", color="#E74C3C")
        if len(rotulos) > 15:
            passo = max(1, len(rotulos) // 15)
            ax.set_xticks(rotulos[::passo])
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.set_title("Despesa x Arrecadação por dia")
        ax.legend(fontsize=8)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self.grafico_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

    def _calcular_periodo(self):
        dias = self.PERIODOS[self.combo_periodo.get()]
        hoje = date.today()
        data_inicio = hoje if dias == 0 else hoje - timedelta(days=dias)
        return data_inicio, hoje

    def _exportar(self, formato: str) -> None:
        try:
            data_inicio, data_fim = self._calcular_periodo()
            pasta = self.entry_pasta.get().strip() or ConfigController.obter("pasta_exportacao")
            agrupamento = self.combo_agrupamento.get()

            if formato == "pdf":
                caminho = RelatorioController.exportar_pdf(data_inicio, data_fim, pasta, agrupamento)
            elif formato == "excel":
                caminho = RelatorioController.exportar_excel(data_inicio, data_fim, pasta, agrupamento)
            else:
                caminho = RelatorioController.exportar_csv(data_inicio, data_fim, pasta, agrupamento)

            self.label_status.configure(text=f"Relatório gerado: {caminho}", text_color="#2ECC71")
            messagebox.showinfo("Sucesso", f"Relatório salvo em:\n{caminho}")
        except Exception as e:
            self.label_status.configure(text=f"Erro ao gerar relatório: {e}", text_color="#E74C3C")
            messagebox.showerror("Erro", f"Não foi possível gerar o relatório:\n{e}")

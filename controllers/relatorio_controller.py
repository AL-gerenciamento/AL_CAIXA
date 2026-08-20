"""
controllers/relatorio_controller.py
Geração de relatórios (CSV, Excel e PDF) agrupados por dia, semana, mês,
ano ou categoria, usando Pandas para exportação tabular e ReportLab para PDF.
"""
from __future__ import annotations

import os
from datetime import date, datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from controllers.receita_controller import ReceitaController
from controllers.despesa_controller import DespesaController
from utils.logger import registrar_erro

from utils.paths import pasta_base
BASE_DIR = pasta_base()


class RelatorioController:
    """Monta DataFrames de movimentações e exporta em múltiplos formatos."""

    AGRUPAMENTOS = ("dia", "semana", "mes", "ano", "categoria")

    @staticmethod
    def _montar_dataframe(data_inicio: date, data_fim: date) -> pd.DataFrame:
        """Combina receitas e despesas do período em um único DataFrame."""
        receitas = ReceitaController.listar(data_inicio=data_inicio, data_fim=data_fim)
        despesas = DespesaController.listar(data_inicio=data_inicio, data_fim=data_fim)

        linhas = []
        for r in receitas:
            linhas.append({
                "Tipo": "Receita", "Descrição": r.descricao, "Valor": r.valor,
                "Data": r.data, "Categoria": r.categoria.nome, "Status": "-",
            })
        for d in despesas:
            linhas.append({
                "Tipo": "Despesa", "Descrição": d.descricao, "Valor": d.valor,
                "Data": d.data, "Categoria": d.categoria.nome,
                "Status": "Paga" if d.paga else "Pendente",
            })
        df = pd.DataFrame(linhas)
        if not df.empty:
            df = df.sort_values("Data")
        return df

    @staticmethod
    def _agrupar(df: pd.DataFrame, agrupamento: str) -> pd.DataFrame:
        """Agrega o DataFrame por dia/semana/mês/ano/categoria."""
        if df.empty:
            return df
        df = df.copy()
        df["Data"] = pd.to_datetime(df["Data"])

        if agrupamento == "categoria":
            chave = "Categoria"
        elif agrupamento == "dia":
            df["Período"] = df["Data"].dt.strftime("%d/%m/%Y")
            chave = "Período"
        elif agrupamento == "semana":
            df["Período"] = df["Data"].dt.strftime("%Y-Semana %U")
            chave = "Período"
        elif agrupamento == "mes":
            df["Período"] = df["Data"].dt.strftime("%m/%Y")
            chave = "Período"
        else:  # ano
            df["Período"] = df["Data"].dt.strftime("%Y")
            chave = "Período"

        resumo = df.groupby([chave, "Tipo"])["Valor"].sum().reset_index()
        return resumo

    @staticmethod
    def exportar_csv(data_inicio: date, data_fim: date, pasta_destino: str,
                      agrupamento: str = "dia") -> str:
        """Exporta o relatório detalhado + resumo agrupado em CSV."""
        try:
            df = RelatorioController._montar_dataframe(data_inicio, data_fim)
            os.makedirs(pasta_destino, exist_ok=True)
            caminho = os.path.join(
                pasta_destino, f"relatorio_{datetime.now():%Y%m%d_%H%M%S}.csv"
            )
            df.to_csv(caminho, index=False, encoding="utf-8-sig", sep=";")
            return caminho
        except Exception as e:
            registrar_erro(e, "exportar_csv")
            raise

    @staticmethod
    def exportar_excel(data_inicio: date, data_fim: date, pasta_destino: str,
                        agrupamento: str = "dia") -> str:
        """Exporta relatório detalhado e resumo agrupado em abas separadas do Excel."""
        try:
            df = RelatorioController._montar_dataframe(data_inicio, data_fim)
            resumo = RelatorioController._agrupar(df, agrupamento)
            os.makedirs(pasta_destino, exist_ok=True)
            caminho = os.path.join(
                pasta_destino, f"relatorio_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
            )
            with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="Detalhado", index=False)
                resumo.to_excel(writer, sheet_name=f"Resumo por {agrupamento}", index=False)
            return caminho
        except Exception as e:
            registrar_erro(e, "exportar_excel")
            raise

    @staticmethod
    def exportar_pdf(data_inicio: date, data_fim: date, pasta_destino: str,
                      agrupamento: str = "dia") -> str:
        """Gera um relatório em PDF com tabela detalhada e totais."""
        try:
            df = RelatorioController._montar_dataframe(data_inicio, data_fim)
            os.makedirs(pasta_destino, exist_ok=True)
            caminho = os.path.join(
                pasta_destino, f"relatorio_{datetime.now():%Y%m%d_%H%M%S}.pdf"
            )

            doc = SimpleDocTemplate(caminho, pagesize=A4)
            styles = getSampleStyleSheet()
            elementos = [
                Paragraph("Relatório Financeiro", styles["Title"]),
                Paragraph(
                    f"Período: {data_inicio:%d/%m/%Y} a {data_fim:%d/%m/%Y}", styles["Normal"]
                ),
                Spacer(1, 0.5 * cm),
            ]

            if df.empty:
                elementos.append(Paragraph("Nenhuma movimentação encontrada.", styles["Normal"]))
            else:
                total_receitas = df.loc[df["Tipo"] == "Receita", "Valor"].sum()
                total_despesas = df.loc[df["Tipo"] == "Despesa", "Valor"].sum()
                saldo = total_receitas - total_despesas

                resumo_texto = (
                    f"Total de Receitas: R$ {total_receitas:,.2f} | "
                    f"Total de Despesas: R$ {total_despesas:,.2f} | "
                    f"Saldo: R$ {saldo:,.2f}"
                )
                elementos.append(Paragraph(resumo_texto, styles["Heading3"]))
                elementos.append(Spacer(1, 0.5 * cm))

                dados_tabela = [["Data", "Tipo", "Descrição", "Categoria", "Valor", "Status"]]
                for _, linha in df.iterrows():
                    data_fmt = pd.to_datetime(linha["Data"]).strftime("%d/%m/%Y")
                    dados_tabela.append([
                        data_fmt, linha["Tipo"], linha["Descrição"], linha["Categoria"],
                        f"R$ {linha['Valor']:,.2f}", linha["Status"],
                    ])

                tabela = Table(dados_tabela, repeatRows=1)
                tabela.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3B8ED0")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ]))
                elementos.append(tabela)

            doc.build(elementos)
            return caminho
        except Exception as e:
            registrar_erro(e, "exportar_pdf")
            raise

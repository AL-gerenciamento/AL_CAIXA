"""
views/despesas_view.py
Tela de gestão de despesas: listagem, filtros, status de pagamento,
criação, edição e exclusão.
"""
from datetime import date, datetime

import customtkinter as ctk
from tkinter import messagebox

from controllers.despesa_controller import DespesaController
from controllers.despesa_fixa_controller import (
    DespesaFixaController, TIPOS_RECORRENCIA, NOMES_DIA_SEMANA,
)
from controllers.categoria_controller import CategoriaController
from controllers.config_controller import ConfigController
from utils.validators import ValidationError

NOMES_TIPO_RECORRENCIA = {
    "diaria": "Diária",
    "semanal": "Semanal",
    "mensal": "Mensal",
    "boleto": "Boleto (mensal com vencimento)",
}


class DespesasView(ctk.CTkFrame):
    """CRUD completo de despesas com pesquisa, filtros e status de pagamento."""

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self.moeda = ConfigController.obter("moeda")
        self.categorias = CategoriaController.listar(tipo="despesa")
        self._construir_layout()
        self._atualizar_lista()

    def _construir_layout(self) -> None:
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=30, pady=(25, 10))

        ctk.CTkLabel(
            topo, text="Despesas", font=ctk.CTkFont(size=26, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(
            topo, text="📅 Despesas Fixas", fg_color="transparent", border_width=1,
            command=self._abrir_despesas_fixas
        ).pack(side="right", padx=(10, 0))
        ctk.CTkButton(
            topo, text="+ Nova Despesa", command=self._abrir_formulario
        ).pack(side="right")

        filtros = ctk.CTkFrame(self, fg_color="transparent")
        filtros.pack(fill="x", padx=30, pady=(0, 10))

        self.entry_pesquisa = ctk.CTkEntry(filtros, placeholder_text="Pesquisar por descrição...", width=220)
        self.entry_pesquisa.pack(side="left", padx=(0, 10))
        self.entry_pesquisa.bind("<KeyRelease>", lambda e: self._atualizar_lista())

        nomes_categorias = ["Todas as categorias"] + [c.nome for c in self.categorias]
        self.combo_categoria = ctk.CTkComboBox(
            filtros, values=nomes_categorias, width=170, command=lambda v: self._atualizar_lista()
        )
        self.combo_categoria.set("Todas as categorias")
        self.combo_categoria.pack(side="left", padx=(0, 10))

        self.combo_status = ctk.CTkComboBox(
            filtros, values=["Todos", "Pendentes", "Pagas"], width=110,
            command=lambda v: self._atualizar_lista()
        )
        self.combo_status.set("Todos")
        self.combo_status.pack(side="left", padx=(0, 10))

        self.entry_data_inicio = ctk.CTkEntry(filtros, placeholder_text="De (dd/mm/aaaa)", width=120)
        self.entry_data_inicio.pack(side="left", padx=(0, 10))

        self.entry_data_fim = ctk.CTkEntry(filtros, placeholder_text="Até (dd/mm/aaaa)", width=120)
        self.entry_data_fim.pack(side="left", padx=(0, 10))

        ctk.CTkButton(filtros, text="Filtrar", width=80, command=self._atualizar_lista).pack(side="left")

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
        apenas_pendentes = self.combo_status.get() == "Pendentes"

        despesas = DespesaController.listar(texto, categoria_id, data_inicio, data_fim, apenas_pendentes)
        if self.combo_status.get() == "Pagas":
            despesas = [d for d in despesas if d.paga]

        if not despesas:
            ctk.CTkLabel(self.lista_frame, text="Nenhuma despesa encontrada.").pack(pady=20)
            return

        cabecalho = ctk.CTkFrame(self.lista_frame, fg_color="transparent")
        cabecalho.pack(fill="x", pady=(0, 5))
        for texto_col, largura in [("Data", 90), ("Descrição", 200), ("Categoria", 120), ("Valor", 110), ("Status", 90)]:
            ctk.CTkLabel(cabecalho, text=texto_col, width=largura, font=ctk.CTkFont(weight="bold")).pack(side="left")

        for despesa in despesas:
            linha = ctk.CTkFrame(self.lista_frame, corner_radius=8)
            linha.pack(fill="x", pady=3)
            ctk.CTkLabel(linha, text=despesa.data.strftime("%d/%m/%Y"), width=90).pack(side="left", padx=5, pady=8)
            ctk.CTkLabel(linha, text=despesa.descricao, width=200, anchor="w").pack(side="left", pady=8)
            ctk.CTkLabel(linha, text=despesa.categoria.nome, width=120).pack(side="left", pady=8)
            ctk.CTkLabel(
                linha, text=f"{self.moeda} {despesa.valor:,.2f}", width=110, text_color="#E74C3C"
            ).pack(side="left", pady=8)

            cor_status = "#2ECC71" if despesa.paga else "#F39C12"
            texto_status = "Paga" if despesa.paga else "Pendente"
            ctk.CTkButton(
                linha, text=texto_status, width=90, fg_color=cor_status, hover=False,
                command=lambda d=despesa: self._alternar_status(d)
            ).pack(side="left", padx=5, pady=8)

            ctk.CTkButton(
                linha, text="✏️", width=35, fg_color="transparent",
                command=lambda d=despesa: self._abrir_formulario(d)
            ).pack(side="right", padx=3)
            ctk.CTkButton(
                linha, text="🗑️", width=35, fg_color="transparent", hover_color="#E74C3C",
                command=lambda d=despesa: self._excluir(d)
            ).pack(side="right", padx=3)

    @staticmethod
    def _parse_data(texto: str):
        if not texto.strip():
            return None
        try:
            return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
        except ValueError:
            return None

    def _alternar_status(self, despesa) -> None:
        DespesaController.alternar_status_pagamento(despesa.id, self.usuario.login)
        self._atualizar_lista()

    def _excluir(self, despesa) -> None:
        if messagebox.askyesno("Confirmar", f"Excluir a despesa '{despesa.descricao}'?"):
            DespesaController.excluir(despesa.id, self.usuario.login)
            self._atualizar_lista()

    def _abrir_formulario(self, despesa=None) -> None:
        FormularioDespesa(self, despesa, self.categorias, self.usuario, self._atualizar_lista)

    def _abrir_despesas_fixas(self) -> None:
        JanelaDespesasFixas(self, self.categorias, self.usuario, self._atualizar_lista)


class FormularioDespesa(ctk.CTkToplevel):
    """Janela modal para criação/edição de despesas."""

    def __init__(self, master, despesa, categorias, usuario, ao_salvar):
        super().__init__(master)
        self.despesa = despesa
        self.categorias = categorias
        self.usuario = usuario
        self.ao_salvar = ao_salvar

        self.title("Editar Despesa" if despesa else "Nova Despesa")
        self.geometry("400x540")
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
            self, values=[c.nome for c in self.categorias], width=320
        )
        self.combo_categoria.pack(pady=8)

        self.check_paga = ctk.CTkCheckBox(self, text="Conta já paga")
        self.check_paga.pack(pady=8, anchor="w", padx=40)

        self.entry_obs = ctk.CTkTextbox(self, width=320, height=80)
        self.entry_obs.pack(pady=8)

        if self.despesa:
            self.entry_descricao.insert(0, self.despesa.descricao)
            self.entry_valor.insert(0, str(self.despesa.valor))
            self.entry_data.insert(0, self.despesa.data.strftime("%d/%m/%Y"))
            self.combo_categoria.set(self.despesa.categoria.nome)
            self.entry_obs.insert("1.0", self.despesa.observacoes)
            if self.despesa.paga:
                self.check_paga.select()
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
            paga = bool(self.check_paga.get())

            if self.despesa:
                DespesaController.editar(
                    self.despesa.id, self.entry_descricao.get(), valor, data_lanc,
                    categoria.id, paga, self.entry_obs.get("1.0", "end").strip(), self.usuario.login,
                )
            else:
                DespesaController.criar(
                    self.entry_descricao.get(), valor, data_lanc, categoria.id,
                    paga, self.entry_obs.get("1.0", "end").strip(), self.usuario.login,
                )
            self.ao_salvar()
            self.destroy()
        except (ValueError, ValidationError) as e:
            messagebox.showwarning("Atenção", str(e) if isinstance(e, ValidationError) else "Verifique os campos numéricos e de data.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")


class JanelaDespesasFixas(ctk.CTkToplevel):
    """Lista as despesas fixas cadastradas e permite criar/editar/pausar/excluir."""

    def __init__(self, master, categorias, usuario, ao_atualizar_despesas):
        super().__init__(master)
        self.categorias = categorias
        self.usuario = usuario
        self.ao_atualizar_despesas = ao_atualizar_despesas  # recarrega a lista de despesas ao fechar

        self.title("Despesas Fixas")
        self.geometry("640x500")
        self.grab_set()
        self._construir_layout()

    def _construir_layout(self) -> None:
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            topo, text="Despesas Fixas", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(
            topo, text="+ Nova Despesa Fixa", command=self._abrir_formulario
        ).pack(side="right")

        self.lista_frame = ctk.CTkScrollableFrame(self)
        self.lista_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self._atualizar_lista()

    def _atualizar_lista(self) -> None:
        for widget in self.lista_frame.winfo_children():
            widget.destroy()

        regras = DespesaFixaController.listar()
        if not regras:
            ctk.CTkLabel(self.lista_frame, text="Nenhuma despesa fixa cadastrada.").pack(pady=20)
            return

        for regra in regras:
            self._criar_linha(regra)

    def _descricao_recorrencia(self, regra) -> str:
        if regra.tipo_recorrencia == "diaria":
            return "Todo dia"
        if regra.tipo_recorrencia == "semanal":
            nome_dia = NOMES_DIA_SEMANA[regra.dia_semana].lower()
            if regra.dia_semana <= 4:  # segunda a sexta
                return f"Toda {nome_dia}-feira"
            return f"Todo {nome_dia}"  # sábado / domingo
        if regra.tipo_recorrencia in ("mensal", "boleto"):
            prefixo = "Vencimento todo dia" if regra.tipo_recorrencia == "boleto" else "Todo dia"
            return f"{prefixo} {regra.dia_mes}"
        return ""

    def _criar_linha(self, regra) -> None:
        linha = ctk.CTkFrame(self.lista_frame, corner_radius=8)
        linha.pack(fill="x", pady=4)

        info = ctk.CTkFrame(linha, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=10, pady=8)

        titulo = regra.descricao
        if not regra.ativa:
            titulo += "  (pausada)"
        ctk.CTkLabel(
            info, text=titulo, font=ctk.CTkFont(weight="bold"),
            text_color=("gray50" if not regra.ativa else None)
        ).pack(anchor="w")
        ctk.CTkLabel(
            info,
            text=(
                f"{NOMES_TIPO_RECORRENCIA[regra.tipo_recorrencia]}  •  "
                f"{self._descricao_recorrencia(regra)}  •  "
                f"{regra.categoria.nome}  •  R$ {regra.valor:,.2f}"
            ),
            text_color=("gray35","gray70"), font=ctk.CTkFont(size=12)
        ).pack(anchor="w")

        acoes = ctk.CTkFrame(linha, fg_color="transparent")
        acoes.pack(side="right", padx=10, pady=8)

        texto_pausa = "Pausar" if regra.ativa else "Reativar"
        ctk.CTkButton(
            acoes, text=texto_pausa, width=80,
            command=lambda r=regra: self._alternar_ativa(r)
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            acoes, text="✏️", width=35, fg_color="transparent",
            command=lambda r=regra: self._abrir_formulario(r)
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            acoes, text="🗑️", width=35, fg_color="transparent", hover_color="#E74C3C",
            command=lambda r=regra: self._excluir(r)
        ).pack(side="left", padx=3)

    def _alternar_ativa(self, regra) -> None:
        DespesaFixaController.alternar_ativa(regra.id, self.usuario.login)
        self._atualizar_lista()

    def _excluir(self, regra) -> None:
        if messagebox.askyesno(
            "Confirmar",
            f"Excluir a despesa fixa '{regra.descricao}'? Os lançamentos já gerados no histórico "
            f"não serão apagados."
        ):
            DespesaFixaController.excluir(regra.id, self.usuario.login)
            self._atualizar_lista()

    def _abrir_formulario(self, regra=None) -> None:
        FormularioDespesaFixa(self, regra, self.categorias, self.usuario, self._ao_salvar_regra)

    def _ao_salvar_regra(self) -> None:
        self._atualizar_lista()
        # Uma nova regra pode já ter uma ocorrência vencida (ex.: data_inicio no passado);
        # gera imediatamente para refletir na lista de despesas.
        DespesaFixaController.gerar_lancamentos_pendentes(self.usuario.login)
        self.ao_atualizar_despesas()

    def destroy(self) -> None:
        super().destroy()


class FormularioDespesaFixa(ctk.CTkToplevel):
    """Janela modal para criação/edição de uma despesa fixa."""

    def __init__(self, master, regra, categorias, usuario, ao_salvar):
        super().__init__(master)
        self.regra = regra
        self.categorias = categorias
        self.usuario = usuario
        self.ao_salvar = ao_salvar

        self.title("Editar Despesa Fixa" if regra else "Nova Despesa Fixa")
        self.geometry("400x640")
        self.resizable(False, False)
        self.grab_set()
        self._construir_layout()

    def _construir_layout(self) -> None:
        ctk.CTkLabel(
            self, text=self.title(), font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 15))

        self.entry_descricao = ctk.CTkEntry(self, placeholder_text="Descrição", width=320)
        self.entry_descricao.pack(pady=6)

        self.entry_valor = ctk.CTkEntry(self, placeholder_text="Valor (ex: 150.00)", width=320)
        self.entry_valor.pack(pady=6)

        self.combo_categoria = ctk.CTkComboBox(
            self, values=[c.nome for c in self.categorias], width=320
        )
        self.combo_categoria.pack(pady=6)

        self.combo_tipo = ctk.CTkComboBox(
            self, values=[NOMES_TIPO_RECORRENCIA[t] for t in TIPOS_RECORRENCIA],
            width=320, command=lambda v: self._atualizar_campos_recorrencia()
        )
        self.combo_tipo.pack(pady=6)

        # Campo específico de "semanal": dia da semana
        self.combo_dia_semana = ctk.CTkComboBox(self, values=NOMES_DIA_SEMANA, width=320)

        # Campo específico de "mensal"/"boleto": dia do mês
        self.entry_dia_mes = ctk.CTkEntry(self, placeholder_text="Dia do mês (1 a 31)", width=320)

        self.frame_campo_recorrencia = ctk.CTkFrame(self, fg_color="transparent", width=320, height=36)
        self.frame_campo_recorrencia.pack(pady=6)
        self.frame_campo_recorrencia.pack_propagate(False)

        self.entry_data_inicio = ctk.CTkEntry(self, placeholder_text="Início (dd/mm/aaaa)", width=320)
        self.entry_data_inicio.pack(pady=6)

        self.entry_data_fim = ctk.CTkEntry(self, placeholder_text="Fim (opcional, dd/mm/aaaa)", width=320)
        self.entry_data_fim.pack(pady=6)

        self.entry_obs = ctk.CTkTextbox(self, width=320, height=70)
        self.entry_obs.pack(pady=6)

        if self.regra:
            self.entry_descricao.insert(0, self.regra.descricao)
            self.entry_valor.insert(0, str(self.regra.valor))
            self.combo_categoria.set(self.regra.categoria.nome)
            self.combo_tipo.set(NOMES_TIPO_RECORRENCIA[self.regra.tipo_recorrencia])
            if self.regra.dia_semana is not None:
                self.combo_dia_semana.set(NOMES_DIA_SEMANA[self.regra.dia_semana])
            if self.regra.dia_mes:
                self.entry_dia_mes.insert(0, str(self.regra.dia_mes))
            self.entry_data_inicio.insert(0, self.regra.data_inicio.strftime("%d/%m/%Y"))
            if self.regra.data_fim:
                self.entry_data_fim.insert(0, self.regra.data_fim.strftime("%d/%m/%Y"))
            self.entry_obs.insert("1.0", self.regra.observacoes)
        else:
            self.combo_tipo.set(NOMES_TIPO_RECORRENCIA["mensal"])
            self.entry_data_inicio.insert(0, date.today().strftime("%d/%m/%Y"))
            if self.categorias:
                self.combo_categoria.set(self.categorias[0].nome)

        self._atualizar_campos_recorrencia()

        ctk.CTkButton(self, text="Salvar", width=320, command=self._salvar).pack(pady=15)

    def _atualizar_campos_recorrencia(self) -> None:
        """Mostra o campo certo (dia da semana ou dia do mês) conforme o tipo escolhido."""
        for widget in self.frame_campo_recorrencia.winfo_children():
            widget.pack_forget()

        tipo = self._tipo_selecionado()
        if tipo == "semanal":
            self.combo_dia_semana.pack(in_=self.frame_campo_recorrencia, fill="x")
            if not self.combo_dia_semana.get():
                self.combo_dia_semana.set(NOMES_DIA_SEMANA[0])
        elif tipo in ("mensal", "boleto"):
            self.entry_dia_mes.pack(in_=self.frame_campo_recorrencia, fill="x")

    def _tipo_selecionado(self) -> str:
        texto = self.combo_tipo.get()
        for chave, nome in NOMES_TIPO_RECORRENCIA.items():
            if nome == texto:
                return chave
        return "mensal"

    @staticmethod
    def _parse_data(texto: str):
        texto = texto.strip()
        if not texto:
            return None
        return datetime.strptime(texto, "%d/%m/%Y").date()

    def _salvar(self) -> None:
        try:
            valor = float(self.entry_valor.get().replace(",", "."))
            categoria = next(
                (c for c in self.categorias if c.nome == self.combo_categoria.get()), None
            )
            if not categoria:
                raise ValidationError("Selecione uma categoria válida.")

            tipo = self._tipo_selecionado()
            dia_semana = None
            dia_mes = None

            if tipo == "semanal":
                dia_semana = NOMES_DIA_SEMANA.index(self.combo_dia_semana.get())
            elif tipo in ("mensal", "boleto"):
                texto_dia = self.entry_dia_mes.get().strip()
                if not texto_dia.isdigit():
                    raise ValidationError("Informe o dia do mês (1 a 31).")
                dia_mes = int(texto_dia)

            data_inicio = self._parse_data(self.entry_data_inicio.get()) or date.today()
            data_fim = self._parse_data(self.entry_data_fim.get())
            observacoes = self.entry_obs.get("1.0", "end").strip()

            if self.regra:
                DespesaFixaController.editar(
                    self.regra.id, self.entry_descricao.get(), valor, categoria.id, tipo,
                    dia_semana, dia_mes, data_fim, observacoes, self.usuario.login,
                )
            else:
                DespesaFixaController.criar(
                    self.entry_descricao.get(), valor, categoria.id, tipo,
                    dia_semana, dia_mes, data_inicio, data_fim, observacoes, self.usuario.login,
                )
            self.ao_salvar()
            self.destroy()
        except (ValueError, ValidationError) as e:
            messagebox.showwarning(
                "Atenção", str(e) if isinstance(e, ValidationError) else "Verifique os campos numéricos e de data."
            )
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

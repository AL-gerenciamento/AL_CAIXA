"""
views/configuracoes_view.py
Tela de configurações: tema, moeda, pasta de exportação, impressão, vendas,
Pix, backup/restauração e administração (organizadas em abas).
"""
import os
import threading
from tkinter import messagebox, filedialog

import customtkinter as ctk

from controllers.config_controller import ConfigController
from controllers.backup_controller import BackupController
from controllers.empresa_controller import EmpresaController
from controllers.pix_controller import PixController, TIPOS_CHAVE
from controllers.sync_controller import sincronizar, resolver_conflito, resolver_duplicata
from database import nuvem_disponivel, testar_conexao_nuvem, DATABASE_URL, USAR_REST_NUVEM
from models import Permissao
from utils.impressora import listar_impressoras
from utils import atualizador, supabase_rest
from utils.nuvem_auth import ativar_com_codigo, ErroAutenticacaoNuvem

FONTE_SECAO = ("weight", "bold")
COR_DESCRICAO = ("gray35", "gray70")


class ConfiguracoesView(ctk.CTkFrame):
    """Tela de preferências do sistema e administração, organizada em abas."""

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self._construir_layout()

    # ------------------------------------------------------------------ #
    # Layout geral
    # ------------------------------------------------------------------ #
    def _construir_layout(self) -> None:
        ctk.CTkLabel(
            self, text="Configurações", font=ctk.CTkFont(size=26, weight="bold")
        ).pack(anchor="w", padx=30, pady=(25, 15))

        abas_titulos = ["Geral", "Impressão", "Vendas"]
        if self.usuario.permissao == Permissao.ADMIN:
            abas_titulos += ["Pix", "Administração"]
        abas_titulos.append("Backup")

        self.tabview = ctk.CTkTabview(self, anchor="w")
        self.tabview.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        for titulo in abas_titulos:
            self.tabview.add(titulo)

        self._aba_geral(self.tabview.tab("Geral"))
        self._aba_impressao(self.tabview.tab("Impressão"))
        self._aba_vendas(self.tabview.tab("Vendas"))
        if self.usuario.permissao == Permissao.ADMIN:
            self._aba_pix(self.tabview.tab("Pix"))
            self._aba_administracao(self.tabview.tab("Administração"))
        self._aba_backup(self.tabview.tab("Backup"))

    @staticmethod
    def _secao(parent, titulo: str, descricao: str | None = None) -> None:
        ctk.CTkLabel(parent, text=titulo, font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=5, pady=(15, 5)
        )
        if descricao:
            ctk.CTkLabel(
                parent, text=descricao, text_color=COR_DESCRICAO,
                wraplength=520, justify="left",
            ).pack(anchor="w", padx=5, pady=(0, 8))

    # ------------------------------------------------------------------ #
    # Aba: Geral
    # ------------------------------------------------------------------ #
    def _aba_geral(self, aba) -> None:
        conteudo = ctk.CTkScrollableFrame(aba, fg_color="transparent")
        conteudo.pack(fill="both", expand=True)

        self._secao(conteudo, "Tema")
        self.combo_tema = ctk.CTkComboBox(
            conteudo, values=["dark", "light", "system"], width=250, command=self._alterar_tema,
            dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"),
        )
        self.combo_tema.set(ConfigController.obter("tema"))
        self.combo_tema.pack(anchor="w", padx=5, pady=(0, 5))

        self._secao(conteudo, "Moeda")
        self.entry_moeda = ctk.CTkEntry(conteudo, width=250)
        self.entry_moeda.insert(0, ConfigController.obter("moeda"))
        self.entry_moeda.pack(anchor="w", padx=5, pady=(0, 5))

        self._secao(conteudo, "Pasta de exportação")
        pasta_frame = ctk.CTkFrame(conteudo, fg_color="transparent")
        pasta_frame.pack(anchor="w", padx=5, pady=(0, 5), fill="x")
        self.entry_pasta = ctk.CTkEntry(pasta_frame, width=350)
        self.entry_pasta.insert(0, ConfigController.obter("pasta_exportacao"))
        self.entry_pasta.pack(side="left")
        ctk.CTkButton(pasta_frame, text="Procurar...", width=100, command=self._escolher_pasta).pack(
            side="left", padx=10
        )

        ctk.CTkButton(
            conteudo, text="Salvar Preferências Gerais", command=self._salvar_preferencias_gerais,
        ).pack(anchor="w", padx=5, pady=(20, 10))

    # ------------------------------------------------------------------ #
    # Aba: Impressão
    # ------------------------------------------------------------------ #
    def _aba_impressao(self, aba) -> None:
        conteudo = ctk.CTkScrollableFrame(aba, fg_color="transparent")
        conteudo.pack(fill="both", expand=True)

        self._secao(
            conteudo, "Tamanho da etiqueta (mm)",
            "Deixe em branco para detectar automaticamente pela impressora. Se a etiqueta"
            " estiver saindo cortada, meça o rolo/etiqueta física e informe aqui.",
        )
        etiqueta_frame = ctk.CTkFrame(conteudo, fg_color="transparent")
        etiqueta_frame.pack(anchor="w", padx=5, pady=(0, 5), fill="x")
        ctk.CTkLabel(etiqueta_frame, text="Largura:").pack(side="left")
        self.entry_etiqueta_largura = ctk.CTkEntry(etiqueta_frame, width=70)
        self.entry_etiqueta_largura.insert(0, ConfigController.obter("etiqueta_largura_mm"))
        self.entry_etiqueta_largura.pack(side="left", padx=(5, 15))
        ctk.CTkLabel(etiqueta_frame, text="Altura:").pack(side="left")
        self.entry_etiqueta_altura = ctk.CTkEntry(etiqueta_frame, width=70)
        self.entry_etiqueta_altura.insert(0, ConfigController.obter("etiqueta_altura_mm"))
        self.entry_etiqueta_altura.pack(side="left", padx=5)

        self._secao(
            conteudo, "Largura do recibo (mm)",
            "Deixe em branco para detectar automaticamente pela impressora de recibo"
            " configurada abaixo. Informe aqui se a bobina não for de 80mm.",
        )
        self.entry_recibo_largura = ctk.CTkEntry(conteudo, width=70)
        self.entry_recibo_largura.insert(0, ConfigController.obter("recibo_largura_mm"))
        self.entry_recibo_largura.pack(anchor="w", padx=5, pady=(0, 5))

        self._secao(
            conteudo, "Impressoras dedicadas",
            "Útil quando há mais de uma impressora conectada (ex.: uma para recibo,"
            " outra para etiqueta), para evitar que um documento saia na impressora errada."
            " Deixe em '(padrão do sistema)' para usar a impressora padrão do Windows.",
        )
        impressoras = ["(padrão do sistema)"] + listar_impressoras()

        impressora_recibo_frame = ctk.CTkFrame(conteudo, fg_color="transparent")
        impressora_recibo_frame.pack(anchor="w", padx=5, pady=(0, 10), fill="x")
        ctk.CTkLabel(impressora_recibo_frame, text="Recibo:", width=100, anchor="w").pack(side="left")
        self.combo_impressora_recibo = ctk.CTkComboBox(
            impressora_recibo_frame, values=impressoras, width=300,
            dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"),
        )
        self.combo_impressora_recibo.set(
            ConfigController.obter("impressora_recibo") or "(padrão do sistema)"
        )
        self.combo_impressora_recibo.pack(side="left")

        impressora_etiqueta_frame = ctk.CTkFrame(conteudo, fg_color="transparent")
        impressora_etiqueta_frame.pack(anchor="w", padx=5, pady=(0, 5), fill="x")
        ctk.CTkLabel(impressora_etiqueta_frame, text="Etiqueta:", width=100, anchor="w").pack(side="left")
        self.combo_impressora_etiqueta = ctk.CTkComboBox(
            impressora_etiqueta_frame, values=impressoras, width=300,
            dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"),
        )
        self.combo_impressora_etiqueta.set(
            ConfigController.obter("impressora_etiqueta") or "(padrão do sistema)"
        )
        self.combo_impressora_etiqueta.pack(side="left")

        ctk.CTkButton(
            conteudo, text="Salvar Preferências de Impressão", command=self._salvar_preferencias_impressao,
        ).pack(anchor="w", padx=5, pady=(20, 10))

    # ------------------------------------------------------------------ #
    # Aba: Vendas (desconto/acréscimo — margens só editáveis pelo admin)
    # ------------------------------------------------------------------ #
    def _aba_vendas(self, aba) -> None:
        conteudo = ctk.CTkScrollableFrame(aba, fg_color="transparent")
        conteudo.pack(fill="both", expand=True)

        if self.usuario.permissao == Permissao.ADMIN:
            self._secao(
                conteudo, "Desconto e Acréscimo",
                "Margens máximas que qualquer usuário pode aplicar no Caixa. Acréscimo"
                " sempre exige justificativa, que fica registrada e visível para você"
                " no histórico de vendas.",
            )
            margens_frame = ctk.CTkFrame(conteudo, fg_color="transparent")
            margens_frame.pack(anchor="w", padx=5, pady=(0, 10), fill="x")
            ctk.CTkLabel(margens_frame, text="Desconto máx. (%):").pack(side="left")
            self.entry_desconto_maximo = ctk.CTkEntry(margens_frame, width=70)
            self.entry_desconto_maximo.insert(0, ConfigController.obter("desconto_maximo_percentual"))
            self.entry_desconto_maximo.pack(side="left", padx=(5, 20))
            ctk.CTkLabel(margens_frame, text="Acréscimo máx. (%):").pack(side="left")
            self.entry_acrescimo_maximo = ctk.CTkEntry(margens_frame, width=70)
            self.entry_acrescimo_maximo.insert(0, ConfigController.obter("acrescimo_maximo_percentual"))
            self.entry_acrescimo_maximo.pack(side="left", padx=5)
            ctk.CTkButton(
                conteudo, text="Salvar Margens", command=self._salvar_margens_desconto,
            ).pack(anchor="w", padx=5, pady=(10, 10))
        else:
            ctk.CTkLabel(
                conteudo,
                text="As margens de desconto e acréscimo do Caixa são definidas pelo"
                     " administrador.",
                text_color=COR_DESCRICAO, wraplength=520, justify="left",
            ).pack(anchor="w", padx=5, pady=(15, 10))

    # ------------------------------------------------------------------ #
    # Aba: Pix (admin)
    # ------------------------------------------------------------------ #
    def _aba_pix(self, aba) -> None:
        conteudo = ctk.CTkScrollableFrame(aba, fg_color="transparent")
        conteudo.pack(fill="both", expand=True)

        self._secao(
            conteudo, "Chave Pix para recebimento",
            "Usada para gerar o QR Code na tela de Caixa/Venda quando o pagamento for Pix.",
        )
        pix_config = PixController.obter_configuracao()

        ctk.CTkLabel(conteudo, text="Tipo de chave").pack(anchor="w", padx=5)
        self.combo_pix_tipo = ctk.CTkComboBox(conteudo, values=TIPOS_CHAVE, width=350)
        self.combo_pix_tipo.set(pix_config["tipo_chave"])
        self.combo_pix_tipo.pack(anchor="w", padx=5, pady=(2, 10))

        ctk.CTkLabel(conteudo, text="Chave Pix (sem pontuação: apenas números, e-mail ou chave aleatória)").pack(
            anchor="w", padx=5
        )
        self.entry_pix_chave = ctk.CTkEntry(conteudo, width=350)
        self.entry_pix_chave.insert(0, pix_config["chave"])
        self.entry_pix_chave.pack(anchor="w", padx=5, pady=(2, 10))

        ctk.CTkLabel(conteudo, text="Nome do recebedor").pack(anchor="w", padx=5)
        self.entry_pix_nome = ctk.CTkEntry(conteudo, width=350)
        self.entry_pix_nome.insert(0, pix_config["nome_recebedor"])
        self.entry_pix_nome.pack(anchor="w", padx=5, pady=(2, 10))

        ctk.CTkLabel(conteudo, text="Cidade do recebedor").pack(anchor="w", padx=5)
        self.entry_pix_cidade = ctk.CTkEntry(conteudo, width=350)
        self.entry_pix_cidade.insert(0, pix_config["cidade"])
        self.entry_pix_cidade.pack(anchor="w", padx=5, pady=(2, 15))

        ctk.CTkButton(conteudo, text="Salvar Chave Pix", command=self._salvar_pix).pack(
            anchor="w", padx=5, pady=(0, 10)
        )

    # ------------------------------------------------------------------ #
    # Aba: Administração (admin)
    # ------------------------------------------------------------------ #
    def _aba_administracao(self, aba) -> None:
        conteudo = ctk.CTkScrollableFrame(aba, fg_color="transparent")
        conteudo.pack(fill="both", expand=True)

        self._secao(
            conteudo, "Gestão de usuários, avisos e pagamento",
            "Disponível na tela 'Administração' no menu lateral.",
        )

        if self.usuario.empresa_id:
            self._secao(
                conteudo, "Logo da Empresa",
                "Aparece no Dashboard de todos os usuários da conta.",
            )
            ctk.CTkButton(
                conteudo, text="Selecionar imagem...", command=self._alterar_logo,
            ).pack(anchor="w", padx=5, pady=(0, 10))

    # ------------------------------------------------------------------ #
    # Aba: Backup
    # ------------------------------------------------------------------ #
    def _aba_backup(self, aba) -> None:
        conteudo = ctk.CTkScrollableFrame(aba, fg_color="transparent")
        conteudo.pack(fill="both", expand=True)

        self._secao(conteudo, "Backup do Banco de Dados")
        botoes_backup = ctk.CTkFrame(conteudo, fg_color="transparent")
        botoes_backup.pack(anchor="w", padx=5, pady=(0, 10))
        ctk.CTkButton(botoes_backup, text="Criar Backup Agora", command=self._criar_backup).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkButton(botoes_backup, text="Restaurar Backup...", command=self._restaurar_backup).pack(
            side="left"
        )

        self._secao(
            conteudo, "Sincronização com a Nuvem",
            "O app funciona 100% offline usando o banco local; a nuvem (se configurada)"
            " só serve para manter uma cópia atualizada e permitir acesso de outras máquinas.",
        )
        nuvem_status_frame = ctk.CTkFrame(conteudo, fg_color="transparent")
        nuvem_status_frame.pack(anchor="w", padx=5, pady=(0, 10), fill="x")
        self.label_status_nuvem = ctk.CTkLabel(nuvem_status_frame, text="", anchor="w")
        self.label_status_nuvem.pack(side="left")

        # Modo REST (Supabase) sem sessão ainda: pede o código de ativação
        # desta instalação (gerado pelo super admin via
        # supabase/provisionar_empresa.py) uma única vez — a Edge Function
        # ativar-empresa cria/renova a credencial técnica sozinha (ver
        # supabase/002_jwt_empresa_id.md). Depois disso o app usa só o
        # refresh_token salvo (cifrado por device_id), nunca mais pede
        # ativação de novo, exceto se o código for revogado.
        self.frame_conectar_nuvem = ctk.CTkFrame(conteudo, fg_color="transparent")
        if USAR_REST_NUVEM and not supabase_rest.configurado():
            self.frame_conectar_nuvem.pack(anchor="w", padx=5, pady=(0, 10), fill="x")
            ctk.CTkLabel(
                self.frame_conectar_nuvem,
                text="Código de ativação desta instalação (fornecido pelo suporte):",
                anchor="w",
            ).pack(anchor="w")
            linha = ctk.CTkFrame(self.frame_conectar_nuvem, fg_color="transparent")
            linha.pack(anchor="w", pady=(4, 0))
            self.entry_codigo_ativacao = ctk.CTkEntry(linha, placeholder_text="XXXX-XXXX", width=160)
            self.entry_codigo_ativacao.pack(side="left", padx=(0, 8))
            ctk.CTkButton(linha, text="Ativar", width=100, command=self._conectar_nuvem).pack(side="left")

        botoes_nuvem = ctk.CTkFrame(conteudo, fg_color="transparent")
        botoes_nuvem.pack(anchor="w", padx=5, pady=(0, 10))
        ctk.CTkButton(botoes_nuvem, text="Testar Conexão", command=self._testar_nuvem).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkButton(botoes_nuvem, text="Sincronizar Agora", command=self._sincronizar_agora).pack(
            side="left"
        )
        self._atualizar_status_nuvem()

        self._secao(
            conteudo, "Atualizações do Sistema",
            f"Versão instalada: {atualizador.versao_atual()}",
        )
        ctk.CTkButton(
            conteudo, text="Verificar Atualização Agora", command=self._verificar_atualizacao_manual
        ).pack(anchor="w", padx=5, pady=(0, 15))

    # ------------------------------------------------------------------ #
    # Ações
    # ------------------------------------------------------------------ #
    def _alterar_logo(self) -> None:
        caminho = filedialog.askopenfilename(
            title="Selecione a logo da empresa",
            filetypes=[("Imagens", "*.png *.jpg *.jpeg"), ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return
        try:
            EmpresaController.definir_logo(self.usuario.empresa_id, caminho)
            messagebox.showinfo("Sucesso", "Logo atualizado! Acesse o Dashboard para visualizar.")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível atualizar a logo:\n{e}")

    def _alterar_tema(self, tema: str) -> None:
        ctk.set_appearance_mode(tema)

    def _escolher_pasta(self) -> None:
        pasta = filedialog.askdirectory()
        if pasta:
            self.entry_pasta.delete(0, "end")
            self.entry_pasta.insert(0, pasta)

    def _salvar_preferencias_gerais(self) -> None:
        ConfigController.definir("tema", self.combo_tema.get())
        ConfigController.definir("moeda", self.entry_moeda.get() or "R$")
        pasta = self.entry_pasta.get().strip()
        os.makedirs(pasta, exist_ok=True)
        ConfigController.definir("pasta_exportacao", pasta)
        messagebox.showinfo("Sucesso", "Preferências salvas com sucesso!")

    def _salvar_preferencias_impressao(self) -> None:
        for chave, entrada, rotulo in (
            ("etiqueta_largura_mm", self.entry_etiqueta_largura, "largura"),
            ("etiqueta_altura_mm", self.entry_etiqueta_altura, "altura"),
            ("recibo_largura_mm", self.entry_recibo_largura, "largura do recibo"),
        ):
            valor = entrada.get().strip().replace(",", ".")
            if not valor:
                ConfigController.definir(chave, "")
                continue
            try:
                if float(valor) <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Atenção", f"Informe um número válido para a {rotulo} da etiqueta.")
                return
            ConfigController.definir(chave, valor)

        for chave, combo in (
            ("impressora_recibo", self.combo_impressora_recibo),
            ("impressora_etiqueta", self.combo_impressora_etiqueta),
        ):
            valor = combo.get().strip()
            ConfigController.definir(chave, "" if valor == "(padrão do sistema)" else valor)

        messagebox.showinfo("Sucesso", "Preferências de impressão salvas com sucesso!")

    def _salvar_margens_desconto(self) -> None:
        for chave, entrada, rotulo in (
            ("desconto_maximo_percentual", self.entry_desconto_maximo, "desconto"),
            ("acrescimo_maximo_percentual", self.entry_acrescimo_maximo, "acréscimo"),
        ):
            valor = entrada.get().strip().replace(",", ".")
            try:
                if not valor or float(valor) < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Atenção", f"Informe um percentual válido para a margem de {rotulo}.")
                return
            ConfigController.definir(chave, valor)
        messagebox.showinfo("Sucesso", "Margens salvas com sucesso!")

    def _salvar_pix(self) -> None:
        try:
            PixController.salvar_configuracao(
                self.entry_pix_chave.get(), self.combo_pix_tipo.get(),
                self.entry_pix_nome.get(), self.entry_pix_cidade.get(),
            )
            messagebox.showinfo("Sucesso", "Chave Pix salva com sucesso!")
        except ValueError as e:
            messagebox.showwarning("Atenção", str(e))

    def _atualizar_status_nuvem(self) -> None:
        if not USAR_REST_NUVEM and not DATABASE_URL:
            self.label_status_nuvem.configure(
                text="⚪ Nuvem não configurada (rodando só localmente).", text_color=COR_DESCRICAO,
            )
        elif USAR_REST_NUVEM and not supabase_rest.configurado():
            self.label_status_nuvem.configure(
                text="🟡 Nuvem configurada, aguardando ativação (informe o código abaixo).",
                text_color="#E6A700",
            )
        elif nuvem_disponivel():
            self.label_status_nuvem.configure(text="🟢 Conectado à nuvem.", text_color="#2ECC71")
        else:
            self.label_status_nuvem.configure(
                text="🔴 Nuvem configurada, mas indisponível agora (sem internet ou servidor fora do ar).",
                text_color="#E74C3C",
            )

    def _conectar_nuvem(self) -> None:
        codigo = self.entry_codigo_ativacao.get().strip()
        if not codigo:
            messagebox.showwarning("Atenção", "Informe o código de ativação fornecido pelo suporte.")
            return
        try:
            ativar_com_codigo(codigo)
        except ErroAutenticacaoNuvem as e:
            messagebox.showerror("Falha ao ativar", str(e))
            return
        self.entry_codigo_ativacao.delete(0, "end")
        self.frame_conectar_nuvem.pack_forget()
        self._atualizar_status_nuvem()
        messagebox.showinfo("Nuvem", "Ativado com sucesso! A partir de agora a sincronização é automática.")

    def _testar_nuvem(self) -> None:
        # Roda em background: testar_conexao_nuvem() faz chamadas de rede
        # (httpx) e pode demorar/travar se a nuvem estiver lenta ou o JWT
        # precisar renovar — rodando na thread principal isso congela a UI.
        def trabalhar():
            ok, mensagem = testar_conexao_nuvem()
            self.after(0, lambda: self._finalizar_teste_nuvem(ok, mensagem))

        threading.Thread(target=trabalhar, daemon=True).start()

    def _finalizar_teste_nuvem(self, ok: bool, mensagem: str) -> None:
        self._atualizar_status_nuvem()
        if ok:
            messagebox.showinfo("Nuvem", mensagem)
        else:
            messagebox.showerror("Falha ao conectar na nuvem", mensagem)

    def _verificar_atualizacao_manual(self) -> None:
        manifesto = atualizador.verificar_atualizacao()
        if not manifesto:
            messagebox.showinfo(
                "Atualização", f"Você já está na versão mais recente ({atualizador.versao_atual()})."
            )
            return
        if not messagebox.askyesno(
            "Atualização disponível",
            f"Nova versão: {manifesto['versao']} (atual: {atualizador.versao_atual()}).\n\n"
            f"{manifesto.get('notas', '')}\n\nAtualizar agora?"
        ):
            return
        try:
            zip_path = atualizador.baixar_atualizacao(manifesto)
            atualizador.aplicar_atualizacao_e_reiniciar(manifesto, zip_path)
        except Exception as e:
            messagebox.showerror("Erro na atualização", str(e))

    def _sincronizar_agora(self) -> None:
        # Mesmo motivo do _testar_nuvem: sincronizar() pode ficar preso
        # esperando o lock do SQLite (se outro sync já estiver rodando) ou
        # em chamadas de rede — na thread principal isso trava a UI.
        def trabalhar():
            try:
                resultado = sincronizar()
            except Exception as e:
                self.after(0, lambda: self._finalizar_sync_erro(e))
                return
            self.after(0, lambda: self._finalizar_sync_ok(resultado))

        threading.Thread(target=trabalhar, daemon=True).start()

    def _finalizar_sync_erro(self, e: Exception) -> None:
        messagebox.showerror("Erro", f"Falha ao sincronizar:\n{e}")
        self._atualizar_status_nuvem()

    def _finalizar_sync_ok(self, resultado: dict) -> None:
        self._atualizar_status_nuvem()
        if resultado.get("ja_em_andamento"):
            messagebox.showinfo("Nuvem", "Já existe uma sincronização em andamento. Aguarde.")
            return
        if not resultado["sincronizado"]:
            messagebox.showwarning("Nuvem indisponível", "Não foi possível conectar à nuvem agora.")
            return
        msg = f"Sincronização concluída. {resultado['aplicados']} registro(s) atualizado(s)."
        if resultado["conflitos"]:
            messagebox.showinfo("Sucesso", msg)
            self._mostrar_conflitos(resultado["conflitos"])
        else:
            messagebox.showinfo("Sucesso", msg)

    def _mostrar_conflitos(self, conflitos: list[dict]) -> None:
        janela = ctk.CTkToplevel(self)
        janela.title(f"Conflitos de sincronização ({len(conflitos)})")
        janela.geometry("640x480")
        janela.transient(self.winfo_toplevel())

        ctk.CTkLabel(
            janela,
            text="Registros alterados dos dois lados. Escolha qual versão manter em cada um:",
            wraplength=600, justify="left",
        ).pack(anchor="w", padx=15, pady=(15, 5))

        lista = ctk.CTkScrollableFrame(janela)
        lista.pack(fill="both", expand=True, padx=15, pady=10)

        def _resumo(dados: dict | None) -> str:
            if dados is None:
                return "(inexistente)"
            campos = [f"{k}={v}" for k, v in dados.items() if k not in ("uuid", "atualizado_em")]
            return " | ".join(campos[:6])

        def _renderizar():
            for w in lista.winfo_children():
                w.destroy()
            if not conflitos:
                ctk.CTkLabel(lista, text="Todos os conflitos foram resolvidos.").pack(pady=20)
                return
            for c in list(conflitos):
                bloco = ctk.CTkFrame(lista)
                bloco.pack(fill="x", pady=6)
                ctk.CTkLabel(
                    bloco, text=f"{c['tabela']}  (uuid {c['uuid'][:8]}...)",
                    font=ctk.CTkFont(weight="bold"),
                ).pack(anchor="w", padx=10, pady=(8, 0))
                ctk.CTkLabel(
                    bloco, text=f"Local: {_resumo(c['local'])}",
                    wraplength=560, justify="left", anchor="w",
                ).pack(anchor="w", padx=10)
                ctk.CTkLabel(
                    bloco, text=f"Nuvem: {_resumo(c['nuvem'])}",
                    wraplength=560, justify="left", anchor="w",
                ).pack(anchor="w", padx=10, pady=(0, 5))

                linha_botoes = ctk.CTkFrame(bloco, fg_color="transparent")
                linha_botoes.pack(anchor="w", padx=10, pady=(0, 8))

                def _resolver(conflito=c, escolha="local"):
                    try:
                        if conflito["local"] is None or conflito["nuvem"] is None:
                            resolver_duplicata(conflito["tabela"], conflito, escolha)
                        else:
                            resolver_conflito(conflito["tabela"], conflito["uuid"], escolha)
                    except Exception as e:
                        messagebox.showerror("Erro", f"Falha ao resolver conflito:\n{e}")
                        return
                    conflitos.remove(conflito)
                    _renderizar()

                if c["local"] is not None:
                    ctk.CTkButton(
                        linha_botoes, text="Manter Local", width=120,
                        command=lambda c=c: _resolver(c, "local"),
                    ).pack(side="left", padx=(0, 8))
                if c["nuvem"] is not None:
                    ctk.CTkButton(
                        linha_botoes, text="Manter Nuvem", width=120,
                        command=lambda c=c: _resolver(c, "nuvem"),
                    ).pack(side="left")

        _renderizar()
        ctk.CTkButton(janela, text="Fechar", command=janela.destroy).pack(pady=(0, 15))

    def _criar_backup(self) -> None:
        try:
            caminho = BackupController.criar_backup(usuario=self.usuario.login)
            messagebox.showinfo("Sucesso", f"Backup criado em:\n{caminho}")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao criar backup:\n{e}")

    def _restaurar_backup(self) -> None:
        caminho = filedialog.askopenfilename(filetypes=[("Banco de dados", "*.db")])
        if not caminho:
            return
        if messagebox.askyesno(
            "Confirmar", "Restaurar este backup substituirá os dados atuais. Continuar?"
        ):
            try:
                BackupController.restaurar_backup(caminho, usuario=self.usuario.login)
                messagebox.showinfo(
                    "Sucesso", "Backup restaurado! Reinicie o aplicativo para aplicar as mudanças."
                )
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao restaurar backup:\n{e}")

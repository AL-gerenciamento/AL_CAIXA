"""
app.py
Janela principal da aplicação: splash screen, login e roteamento
entre a topbar e as telas de conteúdo.
"""
from datetime import date
import threading

import customtkinter as ctk
from tkinter import messagebox

from controllers.config_controller import ConfigController
from controllers.backup_controller import BackupController
from controllers.pagamento_controller import PagamentoController
from controllers.sync_controller import sincronizar, sincronizar_em_tempo_real, definir_empresa_ativa
from controllers.venda_controller import VendaController
from database import registrar_callback_pos_commit_local, USAR_REST_NUVEM
from utils.logger import registrar_erro, registrar_alteracao
from utils import atualizador
from utils.nuvem_auth import renovar_sessao_nuvem

from views.login_view import LoginView
from views.topbar import TopBar
from views.dashboard_view import DashboardView
from views.receitas_view import ReceitasView
from views.despesas_view import DespesasView
from views.categorias_view import CategoriasView
from views.metas_view import MetasView
from views.relatorios_view import RelatoriosView
from views.configuracoes_view import ConfiguracoesView
from views.admin_view import AdminView
from views.pdv_view import PdvView
from views.historico_vendas_view import HistoricoVendasView
from views.produtos_view import ProdutosView
from views.estoque_view import EstoqueView
from views.ajuda_view import AjudaView

# Intervalo entre backups automáticos (em milissegundos): 30 minutos
INTERVALO_BACKUP_AUTOMATICO_MS = 30 * 60 * 1000
# Intervalo de sincronização com a nuvem (em milissegundos): 10 minutos
INTERVALO_SYNC_MS = 30 * 1000
# Intervalo de verificação de bloqueio por pagamento em atraso: 1 hora
INTERVALO_VERIFICACAO_PAGAMENTO_MS = 60 * 60 * 1000

TELAS = {
    "Dashboard": DashboardView,
    "Caixa / Venda": PdvView,
    "Histórico de Vendas": HistoricoVendasView,
    "Produtos": ProdutosView,
    "Estoque e Produção": EstoqueView,
    "Receitas": ReceitasView,
    "Despesas": DespesasView,
    "Categorias": CategoriasView,
    "Metas Financeiras": MetasView,
    "Relatórios": RelatoriosView,
    "Central de Ajuda": AjudaView,
    "Administração": AdminView,
    "Configurações": ConfiguracoesView,
}


class SplashScreen(ctk.CTkToplevel):
    """Tela de abertura exibida brevemente ao iniciar o aplicativo."""

    def __init__(self, master, ao_concluir):
        super().__init__(master)
        self.overrideredirect(True)  # remove bordas da janela
        largura, altura = 420, 260
        self.geometry(self._centralizar(largura, altura))
        self.configure(fg_color=("gray90", "gray10"))

        ctk.CTkLabel(
            self, text="💰", font=ctk.CTkFont(size=60)
        ).pack(pady=(40, 10))
        ctk.CTkLabel(
            self, text="AL Caixa", font=ctk.CTkFont(size=22, weight="bold")
        ).pack()
        ctk.CTkLabel(
            self, text="Carregando...", text_color="gray"
        ).pack(pady=10)
        self.barra = ctk.CTkProgressBar(self, width=280, mode="indeterminate")
        self.barra.pack(pady=15)
        self.barra.start()

        self.after(1500, lambda: self._concluir(ao_concluir))

    def _centralizar(self, largura: int, altura: int) -> str:
        tela_largura = self.winfo_screenwidth()
        tela_altura = self.winfo_screenheight()
        x = (tela_largura - largura) // 2
        y = (tela_altura - altura) // 2
        return f"{largura}x{altura}+{x}+{y}"

    def _concluir(self, ao_concluir) -> None:
        self.barra.stop()
        self.destroy()
        try:
            ao_concluir()
        except Exception as e:
            from utils.logger import registrar_erro
            registrar_erro(e, "splash_concluir")
            self.master.deiconify()
            messagebox.showerror(
                "Erro ao iniciar",
                f"Ocorreu um erro ao abrir o sistema:\n\n{e}\n\nVeja reports\\erros.log para detalhes."
            )


class App(ctk.CTk):
    """Janela raiz: gerencia splash, login e a área principal do sistema."""

    def __init__(self):
        super().__init__()
        self.title("AL Caixa — Gestão Inteligente")
        self.geometry("1200x750")
        self.minsize(1000, 650)

        tema = ConfigController.obter("tema")
        ctk.set_appearance_mode(tema)
        ctk.set_default_color_theme("blue")

        self.usuario_logado = None
        self.topbar = None
        self.tela_atual = None
        self.conteudo_frame = None

        self.withdraw()  # esconde a janela principal enquanto o splash roda
        SplashScreen(self, ao_concluir=self._mostrar_login)

        self._configurar_atalhos()

    # --- Fluxo de telas ---
    def _mostrar_login(self) -> None:
        self.deiconify()
        self._limpar_janela()
        LoginView(self, ao_autenticar=self._entrar_no_sistema)

    def _entrar_no_sistema(self, usuario) -> None:
        self.usuario_logado = usuario
        registrar_alteracao(usuario.login, "Login realizado")
        definir_empresa_ativa(usuario.empresa_id)
        if USAR_REST_NUVEM:
            # Tenta retomar a sessão da nuvem com o refresh_token salvo
            # desta instalação; se não houver (1ª vez) ou tiver expirado
            # de vez, fica sem sincronizar até o admin conectar em
            # Configurações > Backup — nunca bloqueia o login local.
            try:
                renovar_sessao_nuvem()
            except Exception:
                pass
        self._limpar_janela()
        self._construir_area_principal()
        registrar_callback_pos_commit_local(sincronizar_em_tempo_real)
        self._agendar_backup_automatico()
        self._agendar_sincronizacao()
        self._agendar_verificacao_pagamento()
        self._verificar_aviso_vencimento()
        self.after(4000, self._verificar_atualizacao_silenciosa)

    def _construir_area_principal(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # conteudo_frame e status_bar precisam existir ANTES da TopBar, pois
        # a TopBar já dispara a navegação inicial ("Dashboard") durante sua
        # própria construção.
        self.conteudo_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.conteudo_frame.grid(row=1, column=0, sticky="nsew")

        barra_inferior = ctk.CTkFrame(self, height=24, corner_radius=0, fg_color=("gray85", "gray15"))
        barra_inferior.grid(row=2, column=0, sticky="ew")
        barra_inferior.grid_propagate(False)

        sigla_empresa = getattr(self.usuario_logado.empresa, "sigla", "") if self.usuario_logado.empresa_id else ""
        identificador = f"{self.usuario_logado.login}@{sigla_empresa}" if sigla_empresa else self.usuario_logado.login

        self.status_bar = ctk.CTkLabel(barra_inferior, text=f"{identificador}  |  Pronto", anchor="w")
        self.status_bar.pack(side="left", padx=8)

        self.label_relogio = ctk.CTkLabel(barra_inferior, text="", anchor="e")
        self.label_relogio.pack(side="right", padx=8)
        self._identificador_status = identificador
        self._atualizar_relogio()

        self.topbar = TopBar(self, ao_selecionar=self._navegar, usuario=self.usuario_logado)
        self.topbar.grid(row=0, column=0, sticky="new")
        self._navegar("Dashboard")

    def _navegar(self, nome_tela: str) -> None:
        """Troca a tela exibida na área de conteúdo principal."""
        if self.usuario_logado is None:
            return  # ainda na tela de login/splash

        if nome_tela == "__sair__":
            self._fechar()
            return

        if not self.usuario_logado.tem_permissao(nome_tela):
            messagebox.showwarning(
                "Acesso restrito",
                "Você não tem permissão para acessar esta tela. Solicite ao administrador."
            )
            return

        if self.tela_atual:
            self.tela_atual.destroy()

        classe_tela = TELAS.get(nome_tela)
        try:
            if classe_tela is DashboardView:
                self.tela_atual = classe_tela(
                    self.conteudo_frame, ao_navegar=self._navegar, usuario=self.usuario_logado
                )
            else:
                self.tela_atual = classe_tela(self.conteudo_frame, usuario=self.usuario_logado)
            self.tela_atual.pack(fill="both", expand=True)
            self.status_bar.configure(text=f"{self._identificador_status}  |  {nome_tela}")
        except Exception as e:
            registrar_erro(e, f"navegar_para_{nome_tela}")
            self.status_bar.configure(text=f"Erro ao carregar a tela '{nome_tela}'. Veja o log de erros.")

    def _atualizar_relogio(self) -> None:
        from datetime import datetime
        if not hasattr(self, "label_relogio") or not self.label_relogio.winfo_exists():
            return
        self.label_relogio.configure(text=datetime.now().strftime("%H:%M"))
        self.after(1000, self._atualizar_relogio)

    def _limpar_janela(self) -> None:
        for widget in self.winfo_children():
            widget.destroy()

    # --- Atalhos de teclado ---
    def _configurar_atalhos(self) -> None:
        self.bind("<Control-d>", lambda e: self._navegar("Dashboard"))
        self.bind("<Control-r>", lambda e: self._navegar("Receitas"))
        self.bind("<Control-e>", lambda e: self._navegar("Despesas"))
        self.bind("<Control-m>", lambda e: self._navegar("Metas Financeiras"))
        self.bind("<Control-q>", lambda e: self._fechar())
        self.bind("<F3>", lambda e: self._navegar("Caixa / Venda"))
        self.protocol("WM_DELETE_WINDOW", self._fechar)

    def _fechar(self) -> None:
        try:
            sincronizar()
        except Exception as e:
            registrar_erro(e, "sincronizar_ao_fechar")
        self.destroy()

    # --- Backup automático ---
    def _agendar_backup_automatico(self) -> None:
        def executar_backup():
            try:
                BackupController.criar_backup(usuario="sistema (automático)")
            except Exception as e:
                registrar_erro(e, "backup_automatico")
            finally:
                self.after(INTERVALO_BACKUP_AUTOMATICO_MS, executar_backup)

        self.after(INTERVALO_BACKUP_AUTOMATICO_MS, executar_backup)

    # --- Sincronização com a nuvem ---
    def _agendar_sincronizacao(self) -> None:
        def executar_sync():
            # sincronizar() faz chamadas de rede e pode demorar; rodando
            # direto no callback do after() (thread principal do Tkinter)
            # isso trava a janela inteira até terminar — por isso vai pra
            # uma thread separada. As atualizações feitas por sincronizar()
            # são no banco/objetos, não na UI, então não precisa de
            # self.after(0, ...) de volta aqui.
            def trabalhar():
                try:
                    sincronizar()
                    VendaController.limpar_historico_antigo()
                except Exception as e:
                    registrar_erro(e, "sincronizacao_automatica")

            threading.Thread(target=trabalhar, daemon=True).start()
            self.after(INTERVALO_SYNC_MS, executar_sync)

        self.after(INTERVALO_SYNC_MS, executar_sync)

    # --- Atualização automática (verifica manifest.json no Google Drive) ---
    def _verificar_atualizacao_silenciosa(self) -> None:
        import threading

        def checar():
            manifesto = atualizador.verificar_atualizacao()
            if manifesto:
                self.after(0, lambda: self._perguntar_atualizacao(manifesto))

        threading.Thread(target=checar, daemon=True).start()

    def _perguntar_atualizacao(self, manifesto: dict) -> None:
        notas = manifesto.get("notas", "")
        if not messagebox.askyesno(
            "Atualização disponível",
            f"Nova versão do ORVYN disponível: {manifesto['versao']} "
            f"(atual: {atualizador.versao_atual()}).\n\n{notas}\n\n"
            "Deseja atualizar agora? O app fecha e reabre sozinho em alguns segundos."
        ):
            return
        try:
            zip_path = atualizador.baixar_atualizacao(manifesto)
            atualizador.aplicar_atualizacao_e_reiniciar(manifesto, zip_path)
        except Exception as e:
            registrar_erro(e, "atualizacao_automatica")
            messagebox.showerror("Erro na atualização", f"Não foi possível atualizar: {e}")

    # --- Verificação de pagamento em atraso ---
    def _agendar_verificacao_pagamento(self) -> None:
        def executar_verificacao():
            try:
                PagamentoController.gerar_pagamentos_pendentes()
                PagamentoController.verificar_bloqueios()
                PagamentoController.enviar_emails_cobranca()
            except Exception as e:
                registrar_erro(e, "verificacao_pagamento_automatica")
            finally:
                self.after(INTERVALO_VERIFICACAO_PAGAMENTO_MS, executar_verificacao)

        self.after(INTERVALO_VERIFICACAO_PAGAMENTO_MS, executar_verificacao)

    # --- Aviso de vencimento próximo (3 dias antes) ---
    def _verificar_aviso_vencimento(self) -> None:
        chave = "ultimo_aviso_vencimento"
        hoje_str = date.today().isoformat()
        if ConfigController.obter(chave) != hoje_str:
            conta_id = self.usuario_logado.conta_principal_id or self.usuario_logado.id
            pagamento = PagamentoController.pagamento_a_vencer(conta_id)
            if pagamento:
                dias_restantes = (pagamento.vencimento - date.today()).days
                if dias_restantes > 0:
                    texto = f"Sua mensalidade vence em {dias_restantes} dia(s), em {pagamento.vencimento.strftime('%d/%m/%Y')}."
                else:
                    texto = f"Sua mensalidade venceu em {pagamento.vencimento.strftime('%d/%m/%Y')}. Regularize para evitar bloqueio."
                messagebox.showwarning("Aviso de Vencimento", texto)
            ConfigController.definir(chave, hoje_str)
        self.after(INTERVALO_VERIFICACAO_PAGAMENTO_MS, self._verificar_aviso_vencimento)

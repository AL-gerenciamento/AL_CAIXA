"""
views/login_view.py
Tela de login e cadastro do primeiro usuário administrador.
"""
import customtkinter as ctk
from tkinter import messagebox
import threading

from controllers.usuario_controller import UsuarioController
from controllers.empresa_controller import EmpresaController
from controllers.aviso_controller import AvisoController
from controllers.pagamento_controller import PagamentoController
from controllers.sync_controller import sincronizar
from models import Permissao, TipoPessoa
from utils.validators import ValidationError, validar_data
from utils.mascaras import aplicar_mascara_cpf, aplicar_mascara_cnpj, aplicar_mascara_data
from utils import nuvem_auth


class LoginView(ctk.CTkFrame):
    """Tela de autenticação exibida antes de liberar acesso ao sistema."""

    def __init__(self, master, ao_autenticar):
        """
        :param ao_autenticar: callback(usuario) chamado após login bem-sucedido.
        """
        super().__init__(master, fg_color="transparent")
        self.ao_autenticar = ao_autenticar
        self.pack(fill="both", expand=True)
        self._construir_layout()

    def _construir_layout(self) -> None:
        avisos = AvisoController.listar_ativos()
        if avisos:
            avisos_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray90", "gray15"))
            avisos_frame.place(relx=0.5, rely=0.08, anchor="n")
            for aviso in avisos:
                ctk.CTkLabel(
                    avisos_frame, text=f"📢 {aviso.titulo}",
                    font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=("gray10", "gray95"),
                ).pack(anchor="w", padx=20, pady=(12, 0))
                ctk.CTkLabel(
                    avisos_frame, text=aviso.mensagem, wraplength=360, justify="left",
                    text_color=("gray20", "gray85"),
                ).pack(anchor="w", padx=20, pady=(2, 12))

        container = ctk.CTkFrame(self, corner_radius=16, width=380)
        container.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            container, text="AL Caixa",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(padx=40, pady=(30, 5))
        ctk.CTkLabel(
            container, text="Acesse sua conta", text_color=("gray35","gray70")
        ).pack(pady=(0, 20))

        self.entry_login = ctk.CTkEntry(container, placeholder_text="usuario@SIGLA", width=280)
        self.entry_login.pack(padx=40, pady=8)

        self.entry_senha = ctk.CTkEntry(
            container, placeholder_text="Senha", show="•", width=280
        )
        self.entry_senha.pack(padx=40, pady=8)
        self.entry_senha.bind("<Return>", lambda e: self._entrar())

        ctk.CTkButton(container, text="Entrar", width=280, command=self._entrar).pack(
            padx=40, pady=(15, 5)
        )

        # Link "Esqueci minha senha" fica sempre visível
        link_recuperar = ctk.CTkLabel(
            container, text="Esqueci minha senha", text_color=("#3B8ED0", "#6FB3EF"),
            cursor="hand2"
        )
        link_recuperar.pack(pady=(0, 15))
        link_recuperar.bind("<Button-1>", lambda e: self._abrir_recuperacao())

        # O cadastro de empresa (e do seu admin principal) fica sempre
        # disponível: o sistema é multiempresa, então novas empresas podem
        # se cadastrar a qualquer momento. Usuários adicionais dentro de
        # uma empresa já existente são criados pelo painel de Administração,
        # por um administrador já autenticado.
        ctk.CTkButton(
            container, text="Cadastrar minha empresa", width=280,
            fg_color="transparent", border_width=1, command=self._abrir_cadastro
        ).pack(padx=40, pady=(0, 15))

        # Link para instalações novas (PC diferente do que fez o cadastro
        # original): o banco local está vazio, então login normal nunca vai
        # achar o usuário. Precisa autenticar o dispositivo na nuvem com o
        # código de ativação antes de puxar os dados existentes.
        link_ativar = ctk.CTkLabel(
            container, text="Ativar esta instalação (novo computador)",
            text_color=("#3B8ED0", "#6FB3EF"), cursor="hand2", font=ctk.CTkFont(size=11)
        )
        link_ativar.pack(pady=(0, 10))
        link_ativar.bind("<Button-1>", lambda e: self._abrir_ativacao())

        ctk.CTkLabel(
            container,
            text="Login no formato usuario@SIGLA (a sigla é definida no\ncadastro da empresa).",
            text_color=("gray35","gray70"), wraplength=280, justify="center", font=ctk.CTkFont(size=11)
        ).pack(padx=40, pady=(0, 25))

    def _entrar(self) -> None:
        login = self.entry_login.get()
        senha = self.entry_senha.get()
        try:
            usuario = UsuarioController.autenticar(login, senha)
        except ValidationError as e:
            self._tratar_validation_error(login, e)
            return

        if usuario is not None:
            self.ao_autenticar(usuario)
            return

        # Não achou localmente — pode ser um usuário criado em outro PC
        # que ainda não chegou neste banco (sync só roda depois do
        # primeiro login). Tenta sincronizar agora e checa de novo antes
        # de desistir. Roda em thread separada: sincronizar() faz chamadas
        # de rede e travaria a janela toda se rodasse na thread principal.
        self._tentando_nuvem(True)

        def trabalhar():
            try:
                sincronizar()
            except Exception:
                pass  # sem internet/nuvem fora do ar: segue só com o que já tinha localmente
            self.after(0, lambda: self._apos_tentativa_sync(login, senha))

        threading.Thread(target=trabalhar, daemon=True).start()

    def _apos_tentativa_sync(self, login: str, senha: str) -> None:
        self._tentando_nuvem(False)
        try:
            usuario = UsuarioController.autenticar(login, senha)
        except ValidationError as e:
            self._tratar_validation_error(login, e)
            return
        if usuario:
            self.ao_autenticar(usuario)
        else:
            messagebox.showerror("Erro", "Login ou senha inválidos.")

    def _tratar_validation_error(self, login: str, e: ValidationError) -> None:
        mensagem = str(e)
        if "verificado" in mensagem:
            pendente = UsuarioController.usuario_nao_verificado(login)
            if pendente:
                JanelaVerificacaoEmail(self, pendente, ao_verificar=lambda: None)
                return
        if "Mensalidade" in mensagem:
            JanelaBloqueioPagamento(self, login, mensagem)
            return
        messagebox.showerror("Acesso bloqueado", mensagem)

    def _tentando_nuvem(self, ativo: bool) -> None:
        """Feedback visual simples durante a tentativa de sync no login."""
        self.configure(cursor="watch" if ativo else "")
        self.update_idletasks()

    def _abrir_cadastro(self) -> None:
        JanelaCadastroEmpresa(self, ao_criar=self._recarregar)

    def _abrir_recuperacao(self) -> None:
        JanelaRecuperarSenha(self)

    def _abrir_ativacao(self) -> None:
        JanelaAtivarInstalacao(self)

    def _recarregar(self) -> None:
        """Reconstrói a tela de login (ex.: some o botão de criar conta)."""
        for widget in self.winfo_children():
            widget.destroy()
        self._construir_layout()


class JanelaBloqueioPagamento(ctk.CTkToplevel):
    """
    Janela exibida quando o login falha por bloqueio de falta de pagamento,
    oferecendo a opção de solicitar uma prorrogação emergencial de 12h de
    acesso enquanto o pagamento é regularizado.
    """

    def __init__(self, master, login: str, mensagem: str):
        super().__init__(master)
        self.login = login
        self.title("Acesso bloqueado")
        self.geometry("380x320")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(
            self, text="🔒 Acesso bloqueado", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(25, 10))
        ctk.CTkLabel(
            self, text=mensagem, wraplength=320, justify="left"
        ).pack(padx=25, pady=(0, 20))

        self.botao_prorrogacao = ctk.CTkButton(
            self, text="Solicitar prorrogação emergencial (12h)", width=320,
            command=self._solicitar_prorrogacao,
        )
        self.botao_prorrogacao.pack(padx=25, pady=(0, 10))

        ctk.CTkButton(
            self, text="Fechar", width=320, fg_color="transparent", border_width=1,
            command=self.destroy,
        ).pack(padx=25, pady=(0, 20))

    def _solicitar_prorrogacao(self) -> None:
        try:
            PagamentoController.solicitar_prorrogacao_emergencial(self.login)
            self.botao_prorrogacao.configure(state="disabled")
            messagebox.showinfo(
                "Prorrogação concedida",
                "Acesso liberado por 12h. Regularize o pagamento dentro desse "
                "prazo para evitar o bloqueio novamente. Nossa equipe financeira "
                "já foi avisada do seu pedido."
            )
            self.destroy()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível concluir a solicitação: {e}")


class JanelaAtivarInstalacao(ctk.CTkToplevel):
    """
    Janela para autenticar um PC novo (banco local vazio) contra a nuvem
    usando o código de ativação curto (gerado por 004_trigger_codigo_ativacao.sql,
    entregue pelo super admin — ver EmpresaController.cadastrar). Só
    autentica o DISPOSITIVO (JWT/empresa_id); os usuários da empresa
    continuam existindo só na nuvem até o pull abaixo trazê-los pro
    SQLite local. Depois de puxar tudo, o usuário já cadastrado noutro
    PC consegue logar aqui normalmente com a mesma senha de sempre.
    """

    def __init__(self, master):
        super().__init__(master)
        self.master_login = master
        self.title("Ativar Instalação")
        self.geometry("360x260")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(
            self, text="Ativar esta instalação", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(25, 5))
        ctk.CTkLabel(
            self,
            text="Digite o código de ativação da sua empresa\n"
                 "(o mesmo enviado por e-mail ao super admin).\n"
                 "Isso conecta este computador à nuvem e traz\n"
                 "os dados já cadastrados.",
            text_color=("gray35", "gray70"), wraplength=300, justify="center"
        ).pack(padx=20, pady=(0, 15))

        self.entry_codigo = ctk.CTkEntry(self, placeholder_text="XXXX-XXXX", width=280)
        self.entry_codigo.pack(pady=8)
        self.entry_codigo.bind("<Return>", lambda e: self._ativar())

        self.botao_ativar = ctk.CTkButton(self, text="Ativar e sincronizar", width=280, command=self._ativar)
        self.botao_ativar.pack(pady=15)

        self.label_status = ctk.CTkLabel(self, text="", text_color=("gray35", "gray70"))
        self.label_status.pack()

    def _ativar(self) -> None:
        codigo = self.entry_codigo.get().strip()
        if not codigo:
            messagebox.showwarning("Atenção", "Informe o código de ativação.")
            return

        self.botao_ativar.configure(state="disabled")
        self.label_status.configure(text="Ativando dispositivo...")

        def trabalhar():
            try:
                nuvem_auth.ativar_com_codigo(codigo)
            except nuvem_auth.ErroAutenticacaoNuvem as e:
                self.after(0, self._falha_ativacao, str(e))
                return
            except Exception as e:
                self.after(0, self._falha_ativacao, f"Erro inesperado ao ativar: {e}")
                return

            self.after(0, lambda: self.label_status.configure(
                text="Dispositivo ativado. Baixando dados da nuvem..."
            ))

            try:
                sincronizar()
            except Exception as e:
                self.after(0, self._falha_sincronizacao, str(e))
                return

            self.after(0, self._sucesso)

        threading.Thread(target=trabalhar, daemon=True).start()

    def _falha_ativacao(self, mensagem: str) -> None:
        self.botao_ativar.configure(state="normal")
        self.label_status.configure(text="")
        messagebox.showerror("Falha na ativação", mensagem)

    def _falha_sincronizacao(self, mensagem: str) -> None:
        self.botao_ativar.configure(state="normal")
        self.label_status.configure(text="")
        messagebox.showerror(
            "Ativação concluída, sincronização falhou",
            "O dispositivo foi ativado, mas não foi possível baixar os "
            f"dados agora: {mensagem}\n\nTente sincronizar de novo em alguns instantes "
            "(o link 'Ativar esta instalação' pode ser usado de novo, "
            "é seguro repetir)."
        )

    def _sucesso(self) -> None:
        messagebox.showinfo(
            "Instalação ativada",
            "Dados sincronizados com sucesso! Faça login com seu usuário e senha de sempre."
        )
        self.destroy()


class JanelaCadastroUsuario(ctk.CTkToplevel):
    """Janela modal para cadastro de novos usuários."""

    def __init__(self, master, ao_criar, admin_criador=None, mostrar_verificacao=False):
        """
        :param admin_criador: usuário admin logado que está criando um
            sub-usuário. None quando é o cadastro do primeiro administrador.
        :param mostrar_verificacao: se True, abre a etapa de código de
            verificação de e-mail logo após o cadastro.
        """
        super().__init__(master)
        self.ao_criar = ao_criar
        self.admin_criador = admin_criador
        self.mostrar_verificacao = mostrar_verificacao
        self.title("Cadastro de Usuário")
        self.geometry("360x470")
        self.resizable(False, False)
        self.grab_set()  # torna a janela modal

        ctk.CTkLabel(
            self, text="Novo Usuário", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 15))

        self.entry_nome = ctk.CTkEntry(self, placeholder_text="Nome completo", width=280)
        self.entry_nome.pack(pady=8)

        self.entry_login = ctk.CTkEntry(self, placeholder_text="Login", width=280)
        self.entry_login.pack(pady=8)

        self.entry_email = ctk.CTkEntry(self, placeholder_text="E-mail", width=280)
        self.entry_email.pack(pady=8)

        self.entry_senha = ctk.CTkEntry(
            self, placeholder_text="Senha", show="•", width=280
        )
        self.entry_senha.pack(pady=8)

        self.combo_permissao = ctk.CTkComboBox(
            self, values=[Permissao.ADMIN.value, Permissao.USUARIO.value], width=280,
            dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"),
        )
        self.combo_permissao.pack(pady=8)

        ctk.CTkLabel(
            self, text="O e-mail é usado para recuperação de senha.",
            text_color=("gray35","gray70"), font=ctk.CTkFont(size=11)
        ).pack(pady=(0, 5))

        ctk.CTkButton(self, text="Cadastrar", width=280, command=self._cadastrar).pack(
            pady=20
        )

    def _cadastrar(self) -> None:
        try:
            permissao = (
                Permissao.ADMIN
                if self.combo_permissao.get() == Permissao.ADMIN.value
                else Permissao.USUARIO
            )
            usuario = UsuarioController.criar_usuario(
                self.entry_nome.get(), self.entry_login.get(),
                self.entry_senha.get(), self.entry_email.get(), permissao,
                criado_por=self.admin_criador,
            )
            self.ao_criar()
            self.destroy()
            if self.mostrar_verificacao:
                JanelaVerificacaoEmail(self.master, usuario, ao_verificar=lambda: None)
            else:
                messagebox.showinfo(
                    "Sucesso",
                    "Usuário cadastrado! Peça para ele verificar o e-mail antes do primeiro acesso."
                )
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")


class JanelaCadastroEmpresa(ctk.CTkToplevel):
    """
    Janela modal para cadastro de uma nova empresa (tenant) junto com o
    seu usuário administrador principal. Pede primeiro o tipo de pessoa
    (Física ou Jurídica) e então os campos correspondentes.
    """

    def __init__(self, master, ao_criar):
        super().__init__(master)
        self.ao_criar = ao_criar
        self.tipo_pessoa = TipoPessoa.FISICA
        self.title("Cadastro de Empresa")
        self.geometry("400x680")
        self.resizable(False, False)
        self.grab_set()
        self._construir_layout()

    def _construir_layout(self) -> None:
        ctk.CTkLabel(
            self, text="Cadastro de Empresa", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 5))
        ctk.CTkLabel(
            self, text="O responsável cadastrado é criado como Administrador.",
            text_color=("gray35","gray70"), font=ctk.CTkFont(size=11)
        ).pack(pady=(0, 15))

        self.combo_tipo_pessoa = ctk.CTkSegmentedButton(
            self, values=[TipoPessoa.FISICA.value, TipoPessoa.JURIDICA.value],
            command=self._alternar_tipo_pessoa, width=320,
        )
        self.combo_tipo_pessoa.set(TipoPessoa.FISICA.value)
        self.combo_tipo_pessoa.pack(pady=(0, 15))

        # --- Campos comuns: identificação da empresa no sistema ---
        self.entry_nome_empresa = ctk.CTkEntry(self, placeholder_text="Nome da empresa (único)", width=320)
        self.entry_nome_empresa.pack(pady=6)

        self.entry_sigla = ctk.CTkEntry(self, placeholder_text="Sigla da empresa (única, ex.: ABC)", width=320)
        self.entry_sigla.pack(pady=6)

        # --- Campos específicos por tipo de pessoa ---
        self.frame_campos = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_campos.pack(pady=(6, 0))
        self._construir_campos_pessoa_fisica()

        # --- Credenciais do administrador ---
        self.entry_admin_login = ctk.CTkEntry(self, placeholder_text="Login do administrador", width=320)
        self.entry_admin_login.pack(pady=6)

        self.entry_admin_email = ctk.CTkEntry(self, placeholder_text="E-mail do administrador", width=320)
        self.entry_admin_email.pack(pady=6)

        self.entry_admin_senha = ctk.CTkEntry(
            self, placeholder_text="Senha", show="•", width=320
        )
        self.entry_admin_senha.pack(pady=6)

        ctk.CTkLabel(
            self, text="Seu login de acesso será usuario@SIGLA.",
            text_color=("gray35","gray70"), font=ctk.CTkFont(size=11)
        ).pack(pady=(4, 0))

        ctk.CTkButton(self, text="Cadastrar empresa", width=320, command=self._cadastrar).pack(pady=20)

    def _limpar_campos_pessoa(self) -> None:
        for widget in self.frame_campos.winfo_children():
            widget.destroy()

    def _construir_campos_pessoa_fisica(self) -> None:
        self._limpar_campos_pessoa()
        self.entry_nome_completo = ctk.CTkEntry(self.frame_campos, placeholder_text="Nome completo", width=320)
        self.entry_nome_completo.pack(pady=6)
        self.entry_cpf = ctk.CTkEntry(self.frame_campos, placeholder_text="CPF", width=320)
        self.entry_cpf.pack(pady=6)
        aplicar_mascara_cpf(self.entry_cpf)
        self.entry_nascimento = ctk.CTkEntry(
            self.frame_campos, placeholder_text="Data de nascimento (dd/mm/aaaa)", width=320
        )
        self.entry_nascimento.pack(pady=6)
        aplicar_mascara_data(self.entry_nascimento)

    def _construir_campos_pessoa_juridica(self) -> None:
        self._limpar_campos_pessoa()
        self.entry_razao_social = ctk.CTkEntry(self.frame_campos, placeholder_text="Razão Social", width=320)
        self.entry_razao_social.pack(pady=6)
        self.entry_nome_fantasia = ctk.CTkEntry(self.frame_campos, placeholder_text="Nome Fantasia", width=320)
        self.entry_nome_fantasia.pack(pady=6)
        self.entry_cnpj = ctk.CTkEntry(self.frame_campos, placeholder_text="CNPJ", width=320)
        self.entry_cnpj.pack(pady=6)
        aplicar_mascara_cnpj(self.entry_cnpj)

    def _alternar_tipo_pessoa(self, valor: str) -> None:
        if valor == TipoPessoa.FISICA.value:
            self.tipo_pessoa = TipoPessoa.FISICA
            self._construir_campos_pessoa_fisica()
        else:
            self.tipo_pessoa = TipoPessoa.JURIDICA
            self._construir_campos_pessoa_juridica()

    def _cadastrar(self) -> None:
        try:
            kwargs = {}
            if self.tipo_pessoa == TipoPessoa.FISICA:
                data_nasc = validar_data(self.entry_nascimento.get()).date()
                kwargs.update(
                    nome_completo=self.entry_nome_completo.get(),
                    cpf=self.entry_cpf.get(),
                    data_nascimento=data_nasc,
                )
            else:
                kwargs.update(
                    razao_social=self.entry_razao_social.get(),
                    nome_fantasia=self.entry_nome_fantasia.get(),
                    cnpj=self.entry_cnpj.get(),
                )

            empresa, usuario = EmpresaController.cadastrar(
                self.tipo_pessoa,
                self.entry_nome_empresa.get(),
                self.entry_sigla.get(),
                self.entry_admin_login.get(),
                self.entry_admin_senha.get(),
                self.entry_admin_email.get(),
                **kwargs,
            )
            self.ao_criar()
            self.destroy()
            JanelaVerificacaoEmail(self.master, usuario, ao_verificar=lambda: None)
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")


class JanelaVerificacaoEmail(ctk.CTkToplevel):
    """Janela modal para confirmar o código de verificação enviado por e-mail."""

    def __init__(self, master, usuario, ao_verificar):
        super().__init__(master)
        self.usuario = usuario
        self.ao_verificar = ao_verificar
        self.title("Verificar E-mail")
        self.geometry("360x280")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(
            self, text="Verifique seu e-mail", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 5))
        self.label_email = ctk.CTkLabel(
            self, text=f"Enviamos um código de 6 dígitos para\n{usuario.email}",
            text_color=("gray35","gray70"), wraplength=280, justify="center"
        )
        self.label_email.pack(pady=(0, 15))

        self.entry_codigo = ctk.CTkEntry(self, placeholder_text="Código (6 dígitos)", width=280)
        self.entry_codigo.pack(pady=8)
        self.entry_codigo.bind("<Return>", lambda e: self._confirmar())

        ctk.CTkButton(self, text="Confirmar", width=280, command=self._confirmar).pack(pady=15)

        frame_links = ctk.CTkFrame(self, fg_color="transparent")
        frame_links.pack()

        link_reenviar = ctk.CTkLabel(
            frame_links, text="Reenviar código", text_color=("#3B8ED0", "#6FB3EF"),
            cursor="hand2", font=ctk.CTkFont(size=11)
        )
        link_reenviar.pack(side="left", padx=6)
        link_reenviar.bind("<Button-1>", lambda e: self._reenviar())

        link_alterar_email = ctk.CTkLabel(
            frame_links, text="Digitei o e-mail errado", text_color=("#3B8ED0", "#6FB3EF"),
            cursor="hand2", font=ctk.CTkFont(size=11)
        )
        link_alterar_email.pack(side="left", padx=6)
        link_alterar_email.bind("<Button-1>", lambda e: self._abrir_alterar_email())

    def _abrir_alterar_email(self) -> None:
        JanelaAlterarEmailCadastro(self, self.usuario, ao_alterar=self._email_alterado)

    def _email_alterado(self, novo_email: str) -> None:
        self.usuario.email = novo_email
        self.label_email.configure(text=f"Enviamos um código de 6 dígitos para\n{novo_email}")

    def _confirmar(self) -> None:
        try:
            UsuarioController.verificar_codigo_email(self.usuario.id, self.entry_codigo.get())
            messagebox.showinfo("Sucesso", "E-mail verificado! Você já pode fazer login.")
            self.ao_verificar()
            self.destroy()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    def _reenviar(self) -> None:
        try:
            UsuarioController.reenviar_codigo_verificacao(self.usuario.id)
            messagebox.showinfo("Enviado", "Um novo código foi enviado ao seu e-mail.")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível reenviar o código: {e}")


class JanelaAlterarEmailCadastro(ctk.CTkToplevel):
    """Janela modal simples para corrigir o e-mail digitado errado durante
    o cadastro, antes da verificação. Reenvia o código pro e-mail novo."""

    def __init__(self, master, usuario, ao_alterar):
        super().__init__(master)
        self.usuario = usuario
        self.ao_alterar = ao_alterar
        self.title("Alterar E-mail")
        self.geometry("340x220")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(
            self, text="Corrigir e-mail de cadastro", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(20, 5))
        ctk.CTkLabel(
            self, text="Enviaremos um novo código para o e-mail correto.",
            text_color=("gray35","gray70"), wraplength=280, justify="center"
        ).pack(pady=(0, 15))

        self.entry_novo_email = ctk.CTkEntry(self, placeholder_text="Novo e-mail", width=280)
        self.entry_novo_email.pack(pady=8)
        self.entry_novo_email.bind("<Return>", lambda e: self._salvar())

        ctk.CTkButton(self, text="Salvar e reenviar código", width=280, command=self._salvar).pack(pady=15)

    def _salvar(self) -> None:
        try:
            novo_email = UsuarioController.alterar_email_nao_verificado(
                self.usuario.id, self.entry_novo_email.get()
            )
            messagebox.showinfo("Sucesso", f"E-mail atualizado para {novo_email}.\nUm novo código foi enviado.")
            self.ao_alterar(novo_email)
            self.destroy()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")


class JanelaRecuperarSenha(ctk.CTkToplevel):
    """
    Janela modal com o fluxo de recuperação de senha em duas etapas:
    1) informar o e-mail cadastrado (envia código por e-mail)
    2) informar o código recebido + a nova senha
    """

    def __init__(self, master):
        super().__init__(master)
        self.title("Recuperar Senha")
        self.geometry("360x340")
        self.resizable(False, False)
        self.grab_set()

        self.email_solicitado = None
        self._construir_etapa_email()

    # --- Etapa 1: solicitar o código ---
    def _construir_etapa_email(self) -> None:
        self._limpar()

        ctk.CTkLabel(
            self, text="Recuperar Senha", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 5))
        ctk.CTkLabel(
            self, text="Informe o e-mail cadastrado.\nEnviaremos um código de verificação.",
            text_color=("gray35","gray70"), wraplength=280, justify="center"
        ).pack(pady=(0, 15))

        self.entry_email = ctk.CTkEntry(self, placeholder_text="E-mail", width=280)
        self.entry_email.pack(pady=8)
        self.entry_email.bind("<Return>", lambda e: self._enviar_codigo())

        ctk.CTkButton(self, text="Enviar código", width=280, command=self._enviar_codigo).pack(
            pady=20
        )

    def _enviar_codigo(self) -> None:
        email = self.entry_email.get()
        try:
            UsuarioController.solicitar_recuperacao_senha(email)
            self.email_solicitado = email.strip().lower()
            messagebox.showinfo(
                "Verifique seu e-mail",
                "Se este e-mail estiver cadastrado, um código de verificação "
                "foi enviado. O código é válido por 15 minutos."
            )
            self._construir_etapa_codigo()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except RuntimeError as e:
            # Falha ao enviar e-mail (ex.: SMTP não configurado)
            messagebox.showerror("Erro ao enviar e-mail", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    # --- Etapa 2: informar código + nova senha ---
    def _construir_etapa_codigo(self) -> None:
        self._limpar()

        ctk.CTkLabel(
            self, text="Redefinir Senha", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 5))
        ctk.CTkLabel(
            self, text=f"Digite o código enviado para\n{self.email_solicitado}",
            text_color=("gray35","gray70"), wraplength=280, justify="center"
        ).pack(pady=(0, 15))

        self.entry_codigo = ctk.CTkEntry(self, placeholder_text="Código (6 dígitos)", width=280)
        self.entry_codigo.pack(pady=8)

        self.entry_nova_senha = ctk.CTkEntry(
            self, placeholder_text="Nova senha", show="•", width=280
        )
        self.entry_nova_senha.pack(pady=8)
        self.entry_nova_senha.bind("<Return>", lambda e: self._redefinir())

        ctk.CTkButton(self, text="Redefinir senha", width=280, command=self._redefinir).pack(
            pady=15
        )

        link_reenviar = ctk.CTkLabel(
            self, text="Não recebi o código, tentar novamente",
            text_color=("#3B8ED0", "#6FB3EF"), cursor="hand2", font=ctk.CTkFont(size=11)
        )
        link_reenviar.pack()
        link_reenviar.bind("<Button-1>", lambda e: self._construir_etapa_email())

    def _redefinir(self) -> None:
        codigo = self.entry_codigo.get()
        nova_senha = self.entry_nova_senha.get()
        try:
            UsuarioController.redefinir_senha_com_codigo(
                self.email_solicitado, codigo, nova_senha
            )
            messagebox.showinfo("Sucesso", "Senha redefinida com sucesso! Faça login com a nova senha.")
            self.destroy()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    def _limpar(self) -> None:
        for widget in self.winfo_children():
            widget.destroy()

"""
views/admin_view.py
Painel administrativo: usuários e sub-usuários (hierarquia), avisos da
tela de login, e controle de pagamento mensal da conta. Acesso restrito
a administradores.
"""
import io
import os
import shutil
import uuid

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image

from controllers.usuario_controller import UsuarioController
from controllers.pagamento_controller import PagamentoController
from models import Permissao, StatusPagamento, MODULOS_PERMISSAO
from utils.validators import ValidationError
from utils.paths import pasta_base
from views.login_view import JanelaCadastroUsuario

COMPROVANTES_DIR = os.path.join(pasta_base(), "comprovantes")

_DROPDOWN_KW = dict(dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"))


class AdminView(ctk.CTkFrame):
    """
    Tela de administração da EMPRESA do usuário logado: usuários e
    pagamentos. Acesso restrito a usuários com permissão de Administrador.
    Distinta do painel administrativo separado (admin_panel/app.py), que é
    exclusivo do super administrador da plataforma, enxerga todas as
    empresas cadastradas e é o único lugar onde avisos da tela de login
    podem ser criados/editados.
    """

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario_logado = usuario
        self._construir_layout()

    def _construir_layout(self) -> None:
        if self.usuario_logado.permissao != Permissao.ADMIN:
            ctk.CTkLabel(
                self, text="Acesso restrito a administradores.",
                font=ctk.CTkFont(size=16), text_color="orange"
            ).pack(pady=40)
            return

        ctk.CTkLabel(
            self, text="Administração", font=ctk.CTkFont(size=26, weight="bold")
        ).pack(anchor="w", padx=30, pady=(25, 10))

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=30, pady=(0, 25))
        self.tabview.add("Usuários")
        self.tabview.add("Pagamento")

        self._construir_aba_usuarios(self.tabview.tab("Usuários"))
        self._construir_aba_pagamento(self.tabview.tab("Pagamento"))

    # ------------------------------------------------------------------
    # Aba Usuários
    # ------------------------------------------------------------------
    def _construir_aba_usuarios(self, master) -> None:
        cabecalho = ctk.CTkFrame(master, fg_color="transparent")
        cabecalho.pack(fill="x", pady=(10, 10))
        ctk.CTkButton(
            cabecalho, text="+ Novo sub-usuário", width=170, command=self._abrir_cadastro
        ).pack(side="right")

        self.frame_lista = ctk.CTkScrollableFrame(master, fg_color="transparent")
        self.frame_lista.pack(fill="both", expand=True)
        self.frame_lista.grid_columnconfigure(0, weight=1)
        self._carregar_usuarios()

    def _carregar_usuarios(self) -> None:
        for widget in self.frame_lista.winfo_children():
            widget.destroy()

        conta_id = self.usuario_logado.conta_principal_id or self.usuario_logado.id
        usuarios = UsuarioController.listar_por_conta(conta_id)
        if not usuarios:
            ctk.CTkLabel(self.frame_lista, text="Nenhum usuário encontrado.").pack(pady=20)
            return

        for i, usuario in enumerate(usuarios):
            self._criar_linha_usuario(usuario, i)

    def _criar_linha_usuario(self, usuario, row: int) -> None:
        linha = ctk.CTkFrame(self.frame_lista, corner_radius=10)
        linha.grid(row=row, column=0, sticky="ew", pady=5)
        linha.grid_columnconfigure(0, weight=1)

        info_frame = ctk.CTkFrame(linha, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="w", padx=15, pady=10)

        papel = "Conta principal" if usuario.conta_principal_id is None else "Sub-usuário"
        nome_texto = f"{usuario.nome}  •  {papel}"
        if usuario.id == self.usuario_logado.id:
            nome_texto += "  (você)"

        ctk.CTkLabel(
            info_frame, text=nome_texto, font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("gray10", "gray95"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            info_frame, text=f"Login: {usuario.login}   •   E-mail: {usuario.email or '-'}",
            text_color=("gray35","gray70"), font=ctk.CTkFont(size=12)
        ).pack(anchor="w")

        status_partes = ["Ativo" if usuario.ativo else "Inativo"]
        if not usuario.email_verificado:
            status_partes.append("E-mail não verificado")
        if usuario.bloqueado:
            status_partes.append(f"Bloqueado ({usuario.motivo_bloqueio or 'sem motivo'})")
        status_cor = "#c0392b" if (usuario.bloqueado or not usuario.ativo) else "#2fa84f"
        ctk.CTkLabel(
            info_frame, text="  •  ".join(status_partes), text_color=status_cor,
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w")

        acoes_frame = ctk.CTkFrame(linha, fg_color="transparent")
        acoes_frame.grid(row=0, column=1, sticky="e", padx=15, pady=10)

        combo_permissao = ctk.CTkComboBox(
            acoes_frame, values=[Permissao.ADMIN.value, Permissao.USUARIO.value],
            width=140, command=lambda valor, u=usuario: self._alterar_permissao(u, valor),
            **_DROPDOWN_KW,
        )
        combo_permissao.set(usuario.permissao.value)
        combo_permissao.pack(side="left", padx=(0, 8))

        pode_alterar = usuario.id != self.usuario_logado.id

        if usuario.permissao == Permissao.USUARIO:
            ctk.CTkButton(
                acoes_frame, text="Permissões", width=100,
                command=lambda u=usuario: self._abrir_permissoes(u),
            ).pack(side="left", padx=(0, 8))

        texto_bloqueio = "Desbloquear" if usuario.bloqueado else "Bloquear"
        cor_bloqueio = "#2fa84f" if usuario.bloqueado else "#c0392b"
        ctk.CTkButton(
            acoes_frame, text=texto_bloqueio, width=100, fg_color=cor_bloqueio,
            state="normal" if pode_alterar else "disabled",
            command=lambda u=usuario: self._alternar_bloqueio(u),
        ).pack(side="left", padx=(0, 8))

        texto_botao = "Desativar" if usuario.ativo else "Reativar"
        cor_botao = "#c0392b" if usuario.ativo else "#2fa84f"
        ctk.CTkButton(
            acoes_frame, text=texto_botao, width=90, fg_color=cor_botao,
            state="normal" if pode_alterar else "disabled",
            command=lambda u=usuario: self._alternar_status(u),
        ).pack(side="left")

    def _alterar_permissao(self, usuario, valor: str) -> None:
        nova_permissao = Permissao.ADMIN if valor == Permissao.ADMIN.value else Permissao.USUARIO
        try:
            UsuarioController.alterar_permissao(usuario.id, nova_permissao)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível alterar a permissão: {e}")
            self._carregar_usuarios()

    def _alternar_status(self, usuario) -> None:
        try:
            if usuario.ativo:
                if not messagebox.askyesno(
                    "Confirmar", f"Desativar o usuário '{usuario.nome}'? Ele não poderá mais entrar no sistema."
                ):
                    return
                UsuarioController.desativar_usuario(usuario.id)
            else:
                UsuarioController.reativar_usuario(usuario.id)
            self._carregar_usuarios()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível atualizar o status: {e}")

    def _alternar_bloqueio(self, usuario) -> None:
        try:
            if usuario.bloqueado:
                UsuarioController.desbloquear_usuario(usuario.id, self.usuario_logado.login)
            else:
                if not messagebox.askyesno("Confirmar", f"Bloquear o usuário '{usuario.nome}'?"):
                    return
                UsuarioController.bloquear_usuario(
                    usuario.id, "Bloqueado pelo administrador.", self.usuario_logado.login
                )
            self._carregar_usuarios()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível atualizar o bloqueio: {e}")

    def _abrir_permissoes(self, usuario) -> None:
        JanelaPermissoes(self, usuario, ao_salvar=self._carregar_usuarios)

    def _abrir_cadastro(self) -> None:
        JanelaCadastroUsuario(
            self, ao_criar=self._carregar_usuarios, admin_criador=self.usuario_logado
        )

    # ------------------------------------------------------------------
    # Aba Pagamento
    # ------------------------------------------------------------------
    def _construir_aba_pagamento(self, master) -> None:
        valor_mensalidade = PagamentoController.valor_mensalidade_atual()
        codigo_pix_mensalidade = PagamentoController.codigo_pix_mensalidade_atual()

        pix_frame = ctk.CTkFrame(master, corner_radius=10)
        pix_frame.pack(fill="x", pady=(10, 10))
        ctk.CTkLabel(
            pix_frame,
            text=f"Mensalidade: R$ {valor_mensalidade:.2f}".replace(".", ","),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=15, pady=(10, 0))
        ctk.CTkLabel(
            pix_frame, text="Código Pix (copia e cola):", text_color=("gray35", "gray70")
        ).pack(anchor="w", padx=15, pady=(5, 0))
        campo_pix = ctk.CTkEntry(pix_frame, width=500)
        campo_pix.insert(0, codigo_pix_mensalidade)
        campo_pix.configure(state="readonly")
        campo_pix.pack(anchor="w", padx=15, pady=(2, 12), fill="x")

        self._exibir_qrcode_mensalidade(pix_frame, codigo_pix_mensalidade)

        self.frame_pagamento = ctk.CTkScrollableFrame(master, fg_color="transparent")
        self.frame_pagamento.pack(fill="both", expand=True, pady=(0, 0))
        self._carregar_pagamentos()

    def _exibir_qrcode_mensalidade(self, master, codigo_pix_mensalidade: str) -> None:
        try:
            import qrcode
            imagem = qrcode.make(codigo_pix_mensalidade, box_size=6, border=2)
            buffer = io.BytesIO()
            imagem.save(buffer, format="PNG")
            buffer.seek(0)
            foto = Image.open(buffer)
            ctk_img = ctk.CTkImage(light_image=foto, dark_image=foto, size=(180, 180))
            ctk.CTkLabel(master, text="", image=ctk_img).pack(anchor="w", padx=15, pady=(0, 5))
            ctk.CTkLabel(
                master, text="Escaneie com o app do banco para pagar.", text_color=("gray35", "gray70"),
            ).pack(anchor="w", padx=15, pady=(0, 12))
        except ImportError:
            ctk.CTkLabel(
                master, text="QR Code indisponível (biblioteca 'qrcode' não instalada).",
                text_color=("gray35", "gray70"),
            ).pack(anchor="w", padx=15, pady=(0, 12))

    def _carregar_pagamentos(self) -> None:
        for widget in self.frame_pagamento.winfo_children():
            widget.destroy()

        conta_id = self.usuario_logado.conta_principal_id or self.usuario_logado.id
        pagamentos = PagamentoController.listar_por_conta(conta_id)
        if not pagamentos:
            ctk.CTkLabel(self.frame_pagamento, text="Nenhum pagamento gerado ainda.").pack(pady=20)
            return

        cores = {
            StatusPagamento.PAGO: "#2fa84f",
            StatusPagamento.PENDENTE: "#e6a817",
            StatusPagamento.ATRASADO: "#c0392b",
        }

        for pagamento in pagamentos:
            linha = ctk.CTkFrame(self.frame_pagamento, corner_radius=10)
            linha.pack(fill="x", pady=5)
            info = ctk.CTkFrame(linha, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=15, pady=10)
            ctk.CTkLabel(
                info, text=f"Referência {pagamento.referencia}", font=ctk.CTkFont(size=14, weight="bold"),
                text_color=("gray10", "gray95"),
            ).pack(anchor="w")
            ctk.CTkLabel(
                info, text=f"Vencimento: {pagamento.vencimento.strftime('%d/%m/%Y')}",
                text_color=("gray35","gray70"),
            ).pack(anchor="w")

            if pagamento.status == StatusPagamento.PAGO:
                texto_status, cor_status = "Pago", cores[StatusPagamento.PAGO]
            elif pagamento.aguardando_confirmacao:
                texto_status, cor_status = "Em processamento", "#3b8ed0"
            else:
                texto_status, cor_status = pagamento.status.value, cores[pagamento.status]

            ctk.CTkLabel(
                linha, text=texto_status, text_color=cor_status,
                font=ctk.CTkFont(weight="bold"), width=130,
            ).pack(side="right", padx=(0, 15))

            if pagamento.status != StatusPagamento.PAGO and not pagamento.aguardando_confirmacao:
                ctk.CTkButton(
                    linha, text="Enviar comprovante", width=160,
                    command=lambda p=pagamento: self._enviar_comprovante(p),
                ).pack(side="right", padx=(0, 10))

    def _enviar_comprovante(self, pagamento) -> None:
        caminho = filedialog.askopenfilename(
            title="Selecione o comprovante de pagamento",
            filetypes=[
                ("Imagens e PDF", "*.png *.jpg *.jpeg *.pdf"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if not caminho:
            return
        try:
            os.makedirs(COMPROVANTES_DIR, exist_ok=True)
            extensao = os.path.splitext(caminho)[1]
            novo_nome = f"pagamento_{pagamento.id}_{uuid.uuid4().hex[:8]}{extensao}"
            destino = os.path.join(COMPROVANTES_DIR, novo_nome)
            shutil.copy2(caminho, destino)

            PagamentoController.enviar_comprovante_imprensa(
                pagamento.id, destino, self.usuario_logado.login
            )
            messagebox.showinfo(
                "Comprovante enviado",
                "Comprovante enviado. O pagamento ficará em processamento até a "
                "confirmação da equipe financeira."
            )
            self._carregar_pagamentos()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível enviar o comprovante: {e}")


class JanelaPermissoes(ctk.CTkToplevel):
    """
    Janela para o administrador liberar/bloquear, módulo a módulo, o que
    um sub-usuário (permissao=Usuario) pode acessar. Dashboard e Central
    de Ajuda não aparecem aqui pois são sempre liberados (ver
    Usuario.tem_permissao em models.py).
    """

    def __init__(self, master, usuario, ao_salvar=None):
        super().__init__(master)
        self.usuario = usuario
        self.ao_salvar = ao_salvar
        self.checkboxes: dict[str, ctk.CTkCheckBox] = {}

        self.title(f"Permissões — {usuario.nome}")
        self.geometry("380x480")
        self.minsize(340, 380)
        self.transient(master)
        self.grab_set()

        self._construir_layout()

    def _construir_layout(self) -> None:
        ctk.CTkLabel(
            self, text=f"Módulos liberados para {self.usuario.nome.split()[0]}",
            font=ctk.CTkFont(size=15, weight="bold"), wraplength=340, justify="left",
        ).pack(anchor="w", padx=20, pady=(18, 10))

        area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        area.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        liberados = {
            m.strip() for m in (self.usuario.permissoes_modulos or "").split(",") if m.strip()
        }
        for modulo in MODULOS_PERMISSAO:
            var = ctk.BooleanVar(value=modulo in liberados)
            checkbox = ctk.CTkCheckBox(area, text=modulo, variable=var)
            checkbox.pack(anchor="w", pady=6, padx=4)
            self.checkboxes[modulo] = checkbox

        botoes = ctk.CTkFrame(self, fg_color="transparent")
        botoes.pack(fill="x", padx=20, pady=(0, 18))

        ctk.CTkButton(
            botoes, text="Marcar todos", width=110, fg_color="transparent",
            border_width=1, command=self._marcar_todos,
        ).pack(side="left")
        ctk.CTkButton(
            botoes, text="Desmarcar todos", width=120, fg_color="transparent",
            border_width=1, command=self._desmarcar_todos,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            botoes, text="Salvar", width=90, command=self._salvar,
        ).pack(side="right")

    def _marcar_todos(self) -> None:
        for checkbox in self.checkboxes.values():
            checkbox.select()

    def _desmarcar_todos(self) -> None:
        for checkbox in self.checkboxes.values():
            checkbox.deselect()

    def _salvar(self) -> None:
        modulos = [m for m, cb in self.checkboxes.items() if cb.get()]
        try:
            UsuarioController.alterar_permissoes_modulos(self.usuario.id, modulos)
            messagebox.showinfo("Sucesso", "Permissões atualizadas com sucesso!")
            if self.ao_salvar:
                self.ao_salvar()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar as permissões: {e}")

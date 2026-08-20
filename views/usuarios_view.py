"""
views/usuarios_view.py
Tela de gestão de usuários: listar, criar, alterar permissão e
ativar/desativar. Acesso restrito a administradores.
"""
import customtkinter as ctk
from tkinter import messagebox

from controllers.usuario_controller import UsuarioController
from models import Permissao
from utils.validators import ValidationError
from views.login_view import JanelaCadastroUsuario


class UsuariosView(ctk.CTkFrame):
    """Tela de administração de usuários do sistema."""

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

        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            cabecalho, text="Usuários", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(side="left")

        ctk.CTkButton(
            cabecalho, text="+ Novo usuário", width=150, command=self._abrir_cadastro
        ).pack(side="right")

        self.frame_lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.frame_lista.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.frame_lista.grid_columnconfigure(0, weight=1)

        self._carregar_usuarios()

    def _carregar_usuarios(self) -> None:
        for widget in self.frame_lista.winfo_children():
            widget.destroy()

        usuarios = UsuarioController.listar_usuarios()
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

        nome_texto = usuario.nome
        if usuario.id == self.usuario_logado.id:
            nome_texto += "  (você)"

        ctk.CTkLabel(
            info_frame, text=nome_texto, font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            info_frame, text=f"Login: {usuario.login}   •   E-mail: {usuario.email or '-'}",
            text_color="gray", font=ctk.CTkFont(size=12)
        ).pack(anchor="w")

        status_texto = "Ativo" if usuario.ativo else "Inativo"
        status_cor = "#2fa84f" if usuario.ativo else "#c0392b"
        ctk.CTkLabel(
            info_frame, text=status_texto, text_color=status_cor,
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w")

        acoes_frame = ctk.CTkFrame(linha, fg_color="transparent")
        acoes_frame.grid(row=0, column=1, sticky="e", padx=15, pady=10)

        combo_permissao = ctk.CTkComboBox(
            acoes_frame, values=[Permissao.ADMIN.value, Permissao.USUARIO.value],
            width=150,
            command=lambda valor, u=usuario: self._alterar_permissao(u, valor),
        )
        combo_permissao.set(usuario.permissao.value)
        combo_permissao.pack(side="left", padx=(0, 10))

        # Evita que o único admin logado se auto-desative por engano
        pode_alterar_status = usuario.id != self.usuario_logado.id

        texto_botao = "Desativar" if usuario.ativo else "Reativar"
        cor_botao = "#c0392b" if usuario.ativo else "#2fa84f"
        botao_status = ctk.CTkButton(
            acoes_frame, text=texto_botao, width=90, fg_color=cor_botao,
            state="normal" if pode_alterar_status else "disabled",
            command=lambda u=usuario: self._alternar_status(u),
        )
        botao_status.pack(side="left")

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

    def _abrir_cadastro(self) -> None:
        JanelaCadastroUsuario(self, ao_criar=self._carregar_usuarios)

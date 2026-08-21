"""
admin_panel/app.py
Painel administrativo SEPARADO do app principal, exclusivo do super
administrador da plataforma (Aykon). Enxerga TODAS as empresas
cadastradas no sistema e todos os usuários, independentemente da empresa.

Rodar com:
    python admin_panel/app.py

Requer que o super administrador já tenha sido provisionado com
criar_admin_master.py (na raiz do projeto).
"""
import io
import os
import sys
import threading

# Garante que o diretório raiz do projeto (onde ficam database.py, models.py
# etc.) esteja no PYTHONPATH, já que este arquivo mora em admin_panel/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk
from tkinter import messagebox, filedialog
from PIL import Image

from dotenv import load_dotenv
from utils.paths import pasta_base
load_dotenv(os.path.join(pasta_base(), ".env"))

from controllers.usuario_controller import UsuarioController
from controllers.empresa_controller import EmpresaController
from controllers.aviso_controller import AvisoController
from controllers.pagamento_controller import PagamentoController
from controllers.sync_controller import sincronizar, sincronizar_em_tempo_real
from controllers.mensagem_controller import (
    MensagemController, DESTINO_TODOS, DESTINO_ADMINS, DESTINO_EMPRESA, DESTINO_USUARIO,
)
from models import Permissao, StatusPagamento
from utils.validators import ValidationError, validar_data
from utils.logger import registrar_erro
from utils import atualizador
from utils.pix_payload import TIPOS_CHAVE
from database import init_db, registrar_callback_pos_commit_local

_DROPDOWN_KW = dict(dropdown_text_color=("gray10", "gray90"), dropdown_fg_color=("gray95", "gray20"))


class LoginSuperAdmin(ctk.CTkFrame):
    """Tela de login exclusiva do super administrador da plataforma."""

    def __init__(self, master, ao_autenticar):
        super().__init__(master, fg_color="transparent")
        self.ao_autenticar = ao_autenticar
        self.pack(fill="both", expand=True)

        container = ctk.CTkFrame(self, corner_radius=16, width=380)
        container.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            container, text="🛡️ Painel Administrativo", font=ctk.CTkFont(size=24, weight="bold")
        ).pack(padx=40, pady=(30, 5))
        ctk.CTkLabel(
            container, text="Acesso exclusivo do super administrador", text_color="gray"
        ).pack(pady=(0, 20))

        self.entry_login = ctk.CTkEntry(container, placeholder_text="Login", width=280)
        self.entry_login.pack(padx=40, pady=8)

        self.entry_senha = ctk.CTkEntry(container, placeholder_text="Senha", show="•", width=280)
        self.entry_senha.pack(padx=40, pady=8)
        self.entry_senha.bind("<Return>", lambda e: self._entrar())

        ctk.CTkButton(container, text="Entrar", width=280, command=self._entrar).pack(
            padx=40, pady=(15, 30)
        )

    def _entrar(self) -> None:
        login = self.entry_login.get()
        senha = self.entry_senha.get()
        try:
            usuario = UsuarioController.autenticar(login, senha)
        except ValidationError as e:
            messagebox.showerror("Acesso bloqueado", str(e))
            return
        if usuario and usuario.super_admin:
            self.ao_autenticar(usuario)
        else:
            messagebox.showerror("Erro", "Login ou senha inválidos, ou usuário sem permissão de super administrador.")


class PainelSuperAdmin(ctk.CTkFrame):
    """Painel com visão de todas as empresas, usuários, avisos e pagamentos."""

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario_logado = usuario
        self.pack(fill="both", expand=True)
        self._construir_layout()

    def _construir_layout(self) -> None:
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=30, pady=(20, 5))
        ctk.CTkLabel(
            topo, text=f"🛡️ Painel Administrativo — {self.usuario_logado.nome}",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(topo, text="Sincronizar agora", width=150, command=self._sincronizar).pack(side="right")
        ctk.CTkButton(
            topo, text="Verificar atualização do Master", width=210,
            command=lambda: self.master._verificar_atualizacao_silenciosa()
        ).pack(side="right", padx=(0, 10))

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=30, pady=(10, 25))
        self.tabview.add("Empresas")
        self.tabview.add("Usuários")
        self.tabview.add("Avisos")
        self.tabview.add("Pagamentos")
        self.tabview.add("Mensagens")
        self.tabview.add("Atualizações")

        self._construir_aba_empresas(self.tabview.tab("Empresas"))
        self._construir_aba_usuarios(self.tabview.tab("Usuários"))
        self._construir_aba_avisos(self.tabview.tab("Avisos"))
        self._construir_aba_pagamentos(self.tabview.tab("Pagamentos"))
        self._construir_aba_mensagens(self.tabview.tab("Mensagens"))
        self._construir_aba_atualizacoes(self.tabview.tab("Atualizações"))

    def _sincronizar(self) -> None:
        def trabalhar():
            try:
                resultado = sincronizar()
            except Exception as e:
                registrar_erro(e, "sincronizar_painel_admin")
                self.after(0, lambda: messagebox.showerror("Erro", f"Falha ao sincronizar: {e}"))
                return
            self.after(0, lambda: self._apos_sincronizar(resultado))

        threading.Thread(target=trabalhar, daemon=True).start()

    def _apos_sincronizar(self, resultado: dict) -> None:
        if resultado.get("ja_em_andamento"):
            messagebox.showinfo("Sincronização", "Já existe uma sincronização em andamento; aguarde o ciclo atual terminar.")
            return
        if not resultado["sincronizado"]:
            messagebox.showwarning("Sincronização", "Nuvem indisponível no momento.")
            return
        self._carregar_empresas()
        self._carregar_usuarios()
        self._carregar_avisos()
        self._carregar_pagamentos()
        messagebox.showinfo(
            "Sincronização",
            f"{resultado['aplicados']} registro(s) aplicado(s). "
            f"{len(resultado['conflitos'])} conflito(s) pendente(s)."
        )

    # ------------------------------------------------------------------
    # Aba Empresas
    # ------------------------------------------------------------------
    def _construir_aba_empresas(self, master) -> None:
        self.frame_empresas = ctk.CTkScrollableFrame(master, fg_color="transparent")
        self.frame_empresas.pack(fill="both", expand=True, pady=(10, 0))
        self._carregar_empresas()

    def _carregar_empresas(self) -> None:
        for widget in self.frame_empresas.winfo_children():
            widget.destroy()

        empresas = EmpresaController.listar_todas()
        if not empresas:
            ctk.CTkLabel(self.frame_empresas, text="Nenhuma empresa cadastrada.").pack(pady=20)
            return

        for empresa in empresas:
            linha = ctk.CTkFrame(self.frame_empresas, corner_radius=10)
            linha.pack(fill="x", pady=5)
            linha.grid_columnconfigure(0, weight=1)

            info = ctk.CTkFrame(linha, fg_color="transparent")
            info.grid(row=0, column=0, sticky="w", padx=15, pady=10)

            identificacao = (
                empresa.nome_completo if empresa.tipo_pessoa.value == "Pessoa Física"
                else empresa.razao_social
            )
            documento = empresa.cpf or empresa.cnpj or "-"

            ctk.CTkLabel(
                info, text=f"{empresa.nome}  •  {empresa.sigla}",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w")
            ctk.CTkLabel(
                info, text=f"{empresa.tipo_pessoa.value}  •  {identificacao or '-'}  •  Doc: {documento}",
                text_color="gray", font=ctk.CTkFont(size=12)
            ).pack(anchor="w")
            status_nuvem = "☁️ Nuvem liberada" if empresa.nuvem_liberada else "🚫 Nuvem bloqueada"
            cor_status = "#2ECC71" if empresa.nuvem_liberada else "#E74C3C"
            ctk.CTkLabel(
                info, text=status_nuvem, text_color=cor_status, font=ctk.CTkFont(size=12, weight="bold")
            ).pack(anchor="w", pady=(2, 0))

            acoes = ctk.CTkFrame(linha, fg_color="transparent")
            acoes.grid(row=0, column=1, sticky="e", padx=15, pady=10)

            texto_toggle = "🚫 Bloquear nuvem" if empresa.nuvem_liberada else "☁️ Liberar nuvem"
            cor_toggle = "#E67E22" if empresa.nuvem_liberada else "#2ECC71"
            ctk.CTkButton(
                acoes, text=texto_toggle, width=150, fg_color=cor_toggle,
                command=lambda e=empresa: self._alternar_nuvem_empresa(e),
            ).pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                acoes, text="🗑️ Excluir", width=110, fg_color="transparent", hover_color="#E74C3C",
                command=lambda e=empresa: self._excluir_empresa(e),
            ).pack(side="left")

    def _alternar_nuvem_empresa(self, empresa) -> None:
        novo_estado = not empresa.nuvem_liberada
        acao = "liberar o acesso à nuvem" if novo_estado else "BLOQUEAR o acesso à nuvem"
        if not messagebox.askyesno(
            "Confirmar", f"Deseja {acao} para a empresa '{empresa.nome}' ({empresa.sigla})?\n\n"
            "O app local da empresa continua funcionando normalmente offline; "
            "apenas a sincronização/backup em nuvem é afetada."
        ):
            return
        try:
            EmpresaController.definir_nuvem_liberada(empresa.id, novo_estado)
            self._carregar_empresas()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível atualizar: {e}")

    def _excluir_empresa(self, empresa) -> None:
        if not messagebox.askyesno(
            "Confirmar exclusão",
            f"Excluir definitivamente a empresa '{empresa.nome}' ({empresa.sigla}) e "
            f"todos os seus usuários da nuvem?\n\nEsta ação não pode ser desfeita."
        ):
            return
        try:
            EmpresaController.excluir_empresa(empresa.id, self.usuario_logado.login)
            self._carregar_empresas()
            self._carregar_usuarios()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível excluir a empresa: {e}")

    # ------------------------------------------------------------------
    # Aba Usuários (todas as empresas)
    # ------------------------------------------------------------------
    def _construir_aba_usuarios(self, master) -> None:
        self.frame_usuarios = ctk.CTkScrollableFrame(master, fg_color="transparent")
        self.frame_usuarios.pack(fill="both", expand=True, pady=(10, 0))
        self.frame_usuarios.grid_columnconfigure(0, weight=1)
        self._carregar_usuarios()

    def _carregar_usuarios(self) -> None:
        for widget in self.frame_usuarios.winfo_children():
            widget.destroy()

        usuarios = UsuarioController.listar_usuarios()
        if not usuarios:
            ctk.CTkLabel(self.frame_usuarios, text="Nenhum usuário encontrado.").pack(pady=20)
            return

        for i, usuario in enumerate(usuarios):
            self._criar_linha_usuario(usuario, i)

    def _criar_linha_usuario(self, usuario, row: int) -> None:
        linha = ctk.CTkFrame(self.frame_usuarios, corner_radius=10)
        linha.grid(row=row, column=0, sticky="ew", pady=5)
        linha.grid_columnconfigure(0, weight=1)

        info_frame = ctk.CTkFrame(linha, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="w", padx=15, pady=10)

        if usuario.super_admin:
            empresa_texto = "Plataforma (equipe de integração)"
        elif usuario.empresa is not None:
            empresa_texto = f"{usuario.empresa.nome} ({usuario.empresa.sigla})"
        else:
            empresa_texto = "-"

        ctk.CTkLabel(
            info_frame, text=f"{usuario.nome}  •  {empresa_texto}",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            info_frame, text=f"Login: {usuario.login_completo}   •   E-mail: {usuario.email or '-'}",
            text_color="gray", font=ctk.CTkFont(size=12)
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

        if usuario.super_admin:
            return  # o super admin não gerencia a própria conta por aqui

        acoes_frame = ctk.CTkFrame(linha, fg_color="transparent")
        acoes_frame.grid(row=0, column=1, sticky="e", padx=15, pady=10)

        combo_permissao = ctk.CTkComboBox(
            acoes_frame, values=[Permissao.ADMIN.value, Permissao.USUARIO.value],
            width=140, command=lambda valor, u=usuario: self._alterar_permissao(u, valor),
            **_DROPDOWN_KW,
        )
        combo_permissao.set(usuario.permissao.value)
        combo_permissao.pack(side="left", padx=(0, 8))

        texto_bloqueio = "Desbloquear" if usuario.bloqueado else "Bloquear"
        cor_bloqueio = "#2fa84f" if usuario.bloqueado else "#c0392b"
        ctk.CTkButton(
            acoes_frame, text=texto_bloqueio, width=100, fg_color=cor_bloqueio,
            command=lambda u=usuario: self._alternar_bloqueio(u),
        ).pack(side="left", padx=(0, 8))

        texto_botao = "Desativar" if usuario.ativo else "Reativar"
        cor_botao = "#c0392b" if usuario.ativo else "#2fa84f"
        ctk.CTkButton(
            acoes_frame, text=texto_botao, width=90, fg_color=cor_botao,
            command=lambda u=usuario: self._alternar_status(u),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            acoes_frame, text="🗑️ Excluir", width=100, fg_color="transparent", hover_color="#E74C3C",
            command=lambda u=usuario: self._excluir_usuario(u),
        ).pack(side="left")

    def _alterar_permissao(self, usuario, valor: str) -> None:
        nova = Permissao.ADMIN if valor == Permissao.ADMIN.value else Permissao.USUARIO
        try:
            UsuarioController.alterar_permissao(usuario.id, nova)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível alterar a permissão: {e}")
            self._carregar_usuarios()

    def _alternar_status(self, usuario) -> None:
        try:
            if usuario.ativo:
                if not messagebox.askyesno("Confirmar", f"Desativar o usuário '{usuario.nome}'?"):
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
                    usuario.id, "Bloqueado pelo super administrador.", self.usuario_logado.login
                )
            self._carregar_usuarios()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível atualizar o bloqueio: {e}")

    def _excluir_usuario(self, usuario) -> None:
        if not messagebox.askyesno(
            "Confirmar exclusão",
            f"Excluir definitivamente o usuário '{usuario.nome}' da nuvem?\n\n"
            f"Esta ação não pode ser desfeita."
        ):
            return
        try:
            UsuarioController.excluir_usuario(usuario.id, self.usuario_logado.login)
            self._carregar_usuarios()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível excluir o usuário: {e}")

    # ------------------------------------------------------------------
    # Aba Avisos (globais, exibidos na tela de login de todos)
    # ------------------------------------------------------------------
    def _construir_aba_avisos(self, master) -> None:
        topo = ctk.CTkFrame(master, fg_color="transparent")
        topo.pack(fill="x", pady=(10, 10))
        ctk.CTkButton(topo, text="+ Novo aviso", width=140, command=self._abrir_formulario_aviso).pack(side="right")

        self.frame_avisos = ctk.CTkScrollableFrame(master, fg_color="transparent")
        self.frame_avisos.pack(fill="both", expand=True)
        self._carregar_avisos()

    def _carregar_avisos(self) -> None:
        for widget in self.frame_avisos.winfo_children():
            widget.destroy()

        avisos = AvisoController.listar_todos()
        if not avisos:
            ctk.CTkLabel(self.frame_avisos, text="Nenhum aviso cadastrado.").pack(pady=20)
            return

        for aviso in avisos:
            linha = ctk.CTkFrame(self.frame_avisos, corner_radius=10)
            linha.pack(fill="x", pady=5)
            info = ctk.CTkFrame(linha, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=15, pady=10)
            ctk.CTkLabel(
                info, text=aviso.titulo, font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w")
            ctk.CTkLabel(info, text=aviso.mensagem, text_color="gray", wraplength=500, justify="left").pack(anchor="w")

            status = "Ativo" if aviso.ativo else "Inativo"
            ctk.CTkButton(
                linha, text=status, width=90,
                fg_color="#2fa84f" if aviso.ativo else "#c0392b",
                command=lambda a=aviso: self._alternar_aviso(a),
            ).pack(side="right", padx=(0, 8))
            ctk.CTkButton(
                linha, text="🗑️", width=35, fg_color="transparent", hover_color="#E74C3C",
                command=lambda a=aviso: self._excluir_aviso(a),
            ).pack(side="right", padx=(0, 10))

    def _alternar_aviso(self, aviso) -> None:
        AvisoController.alternar_ativo(aviso.id, self.usuario_logado.login)
        self._carregar_avisos()

    def _excluir_aviso(self, aviso) -> None:
        if messagebox.askyesno("Confirmar", f"Excluir o aviso '{aviso.titulo}'?"):
            AvisoController.excluir(aviso.id, self.usuario_logado.login)
            self._carregar_avisos()

    def _abrir_formulario_aviso(self) -> None:
        FormularioAviso(self, self.usuario_logado, self._carregar_avisos)

    # ------------------------------------------------------------------
    # Aba Pagamentos (de todas as contas)
    # ------------------------------------------------------------------
    def _construir_aba_pagamentos(self, master) -> None:
        self._construir_bloco_mensalidade(master)

        self.frame_pagamentos = ctk.CTkScrollableFrame(master, fg_color="transparent")
        self.frame_pagamentos.pack(fill="both", expand=True, pady=(10, 0))
        self._carregar_pagamentos()

    # --- Configuração da mensalidade da plataforma (valor + Pix) ---
    def _construir_bloco_mensalidade(self, master) -> None:
        bloco = ctk.CTkFrame(master, corner_radius=10)
        bloco.pack(fill="x", pady=(10, 5))

        ctk.CTkLabel(
            bloco, text="Mensalidade da plataforma", font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w", padx=15, pady=(12, 8))

        corpo = ctk.CTkFrame(bloco, fg_color="transparent")
        corpo.pack(fill="x", padx=15, pady=(0, 5))

        coluna_form = ctk.CTkFrame(corpo, fg_color="transparent")
        coluna_form.pack(side="left", fill="x", expand=True)

        linha_valor = ctk.CTkFrame(coluna_form, fg_color="transparent")
        linha_valor.pack(fill="x", pady=4)
        ctk.CTkLabel(linha_valor, text="Valor (R$):", width=140, anchor="w").pack(side="left")
        self.entry_msl_valor = ctk.CTkEntry(linha_valor, width=140)
        self.entry_msl_valor.pack(side="left")

        linha_chave = ctk.CTkFrame(coluna_form, fg_color="transparent")
        linha_chave.pack(fill="x", pady=4)
        ctk.CTkLabel(linha_chave, text="Chave Pix:", width=140, anchor="w").pack(side="left")
        self.entry_msl_chave = ctk.CTkEntry(linha_chave, width=280)
        self.entry_msl_chave.pack(side="left")

        linha_tipo = ctk.CTkFrame(coluna_form, fg_color="transparent")
        linha_tipo.pack(fill="x", pady=4)
        ctk.CTkLabel(linha_tipo, text="Tipo da chave:", width=140, anchor="w").pack(side="left")
        self.combo_msl_tipo = ctk.CTkComboBox(linha_tipo, values=TIPOS_CHAVE, width=180, **_DROPDOWN_KW)
        self.combo_msl_tipo.pack(side="left")

        linha_nome = ctk.CTkFrame(coluna_form, fg_color="transparent")
        linha_nome.pack(fill="x", pady=4)
        ctk.CTkLabel(linha_nome, text="Nome do recebedor:", width=140, anchor="w").pack(side="left")
        self.entry_msl_nome = ctk.CTkEntry(linha_nome, width=280)
        self.entry_msl_nome.pack(side="left")

        linha_cidade = ctk.CTkFrame(coluna_form, fg_color="transparent")
        linha_cidade.pack(fill="x", pady=4)
        ctk.CTkLabel(linha_cidade, text="Cidade:", width=140, anchor="w").pack(side="left")
        self.entry_msl_cidade = ctk.CTkEntry(linha_cidade, width=280)
        self.entry_msl_cidade.pack(side="left")

        rodape = ctk.CTkFrame(coluna_form, fg_color="transparent")
        rodape.pack(fill="x", pady=(8, 4))
        self.label_msl_status = ctk.CTkLabel(rodape, text="", text_color="gray")
        self.label_msl_status.pack(side="left")
        ctk.CTkButton(
            rodape, text="Salvar alterações", width=160, command=self._salvar_mensalidade
        ).pack(side="right")

        self.frame_msl_preview = ctk.CTkFrame(corpo, fg_color="transparent", width=180)
        self.frame_msl_preview.pack(side="right", padx=(20, 0))

        self._carregar_bloco_mensalidade()

    def _carregar_bloco_mensalidade(self) -> None:
        config = PagamentoController.obter_configuracao_mensalidade()
        self.entry_msl_valor.delete(0, "end")
        self.entry_msl_valor.insert(0, f"{config['valor']:.2f}".replace(".", ","))
        self.entry_msl_chave.delete(0, "end")
        self.entry_msl_chave.insert(0, config["pix_chave"])
        self.combo_msl_tipo.set(config["pix_tipo_chave"] or TIPOS_CHAVE[0])
        self.entry_msl_nome.delete(0, "end")
        self.entry_msl_nome.insert(0, config["pix_nome_recebedor"])
        self.entry_msl_cidade.delete(0, "end")
        self.entry_msl_cidade.insert(0, config["pix_cidade"])
        self._atualizar_preview_mensalidade()

    def _atualizar_preview_mensalidade(self) -> None:
        for widget in self.frame_msl_preview.winfo_children():
            widget.destroy()
        try:
            codigo = PagamentoController.codigo_pix_mensalidade_atual()
            import qrcode
            imagem = qrcode.make(codigo, box_size=4, border=2)
            buffer = io.BytesIO()
            imagem.save(buffer, format="PNG")
            buffer.seek(0)
            foto = Image.open(buffer)
            ctk_img = ctk.CTkImage(light_image=foto, dark_image=foto, size=(130, 130))
            ctk.CTkLabel(self.frame_msl_preview, text="", image=ctk_img).pack()
            ctk.CTkLabel(
                self.frame_msl_preview, text="QR Code atual", text_color="gray",
                font=ctk.CTkFont(size=11),
            ).pack(pady=(4, 0))
        except Exception:
            ctk.CTkLabel(
                self.frame_msl_preview, text="QR Code indisponível", text_color="gray"
            ).pack()

    def _salvar_mensalidade(self) -> None:
        valor_texto = self.entry_msl_valor.get().strip().replace(".", "").replace(",", ".")
        try:
            valor = float(valor_texto)
        except ValueError:
            messagebox.showwarning("Atenção", "Informe um valor de mensalidade válido.")
            return

        try:
            PagamentoController.definir_configuracao_mensalidade(
                valor=valor,
                pix_chave=self.entry_msl_chave.get(),
                pix_tipo_chave=self.combo_msl_tipo.get(),
                pix_nome_recebedor=self.entry_msl_nome.get(),
                pix_cidade=self.entry_msl_cidade.get(),
                usuario=self.usuario_logado.login,
            )
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
            return
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar: {e}")
            return

        self._carregar_bloco_mensalidade()
        self.label_msl_status.configure(text="Salvo — sincronizando com a nuvem...")
        self.after(4000, lambda: self.label_msl_status.configure(text=""))

    def _carregar_pagamentos(self) -> None:
        for widget in self.frame_pagamentos.winfo_children():
            widget.destroy()

        pagamentos = PagamentoController.listar_todos()
        if not pagamentos:
            ctk.CTkLabel(self.frame_pagamentos, text="Nenhum pagamento gerado ainda.").pack(pady=20)
            return

        cores = {
            StatusPagamento.PAGO: "#2fa84f",
            StatusPagamento.PENDENTE: "#e6a817",
            StatusPagamento.ATRASADO: "#c0392b",
        }

        for pagamento in pagamentos:
            linha = ctk.CTkFrame(self.frame_pagamentos, corner_radius=10)
            linha.pack(fill="x", pady=5)
            info = ctk.CTkFrame(linha, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=15, pady=10)
            ctk.CTkLabel(
                info, text=f"Conta #{pagamento.conta_principal_id}  •  Referência {pagamento.referencia}",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w")
            ctk.CTkLabel(
                info, text=f"Vencimento: {pagamento.vencimento.strftime('%d/%m/%Y')}", text_color="gray",
            ).pack(anchor="w")
            if pagamento.aguardando_confirmacao and pagamento.comprovante_path:
                ctk.CTkLabel(
                    info, text=f"Comprovante: {pagamento.comprovante_path}", text_color="gray",
                    font=ctk.CTkFont(size=11),
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

            if pagamento.status != StatusPagamento.PAGO:
                texto_botao = "Confirmar pagamento" if pagamento.aguardando_confirmacao else "Marcar como pago"
                ctk.CTkButton(
                    linha, text=texto_botao, width=160,
                    command=lambda p=pagamento: self._marcar_pago(p),
                ).pack(side="right", padx=(0, 10))

    def _marcar_pago(self, pagamento) -> None:
        try:
            PagamentoController.marcar_pago(pagamento.id, self.usuario_logado.login)
            self._carregar_pagamentos()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))

    # ------------------------------------------------------------------
    # Aba Mensagens (e-mail em massa: todos, só admins, uma empresa ou um usuário)
    # ------------------------------------------------------------------
    _MSG_DESTINOS = {
        "Todos os usuários": DESTINO_TODOS,
        "Somente administradores": DESTINO_ADMINS,
        "Uma empresa": DESTINO_EMPRESA,
        "Um usuário": DESTINO_USUARIO,
    }

    def _construir_aba_mensagens(self, master) -> None:
        wrapper = ctk.CTkScrollableFrame(master, fg_color="transparent")
        wrapper.pack(fill="both", expand=True, pady=(10, 0))

        ctk.CTkLabel(
            wrapper, text="Enviar mensagem por e-mail", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", pady=(0, 12))

        linha_destino = ctk.CTkFrame(wrapper, fg_color="transparent")
        linha_destino.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(linha_destino, text="Destinatários:").pack(side="left", padx=(0, 10))
        self.combo_msg_destino = ctk.CTkComboBox(
            linha_destino, values=list(self._MSG_DESTINOS.keys()), width=210,
            command=self._msg_destino_alterado, **_DROPDOWN_KW,
        )
        self.combo_msg_destino.set("Todos os usuários")
        self.combo_msg_destino.pack(side="left")

        self._msg_alvo_por_label: dict[str, int] = {}
        self.combo_msg_alvo = ctk.CTkComboBox(linha_destino, values=[], width=300, **_DROPDOWN_KW)
        # só aparece quando o destino é "Uma empresa" ou "Um usuário"

        ctk.CTkLabel(wrapper, text="Assunto:").pack(anchor="w")
        self.entry_msg_assunto = ctk.CTkEntry(wrapper, placeholder_text="Assunto do e-mail")
        self.entry_msg_assunto.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(wrapper, text="Mensagem:").pack(anchor="w")
        self.texto_msg_corpo = ctk.CTkTextbox(wrapper, height=220)
        self.texto_msg_corpo.pack(fill="both", expand=True, pady=(2, 12))

        rodape = ctk.CTkFrame(wrapper, fg_color="transparent")
        rodape.pack(fill="x")
        self.label_msg_status = ctk.CTkLabel(rodape, text="", text_color="gray")
        self.label_msg_status.pack(side="left")
        self.botao_msg_enviar = ctk.CTkButton(
            rodape, text="Enviar", width=130, command=self._enviar_mensagem
        )
        self.botao_msg_enviar.pack(side="right")

    # ------------------------------------------------------------------
    # Aba Atualizações (gera o manifest.json que vai pro Google Drive)
    # ------------------------------------------------------------------
    def _construir_aba_atualizacoes(self, master) -> None:
        wrapper = ctk.CTkScrollableFrame(master, fg_color="transparent")
        wrapper.pack(fill="both", expand=True, pady=(10, 0))

        ctk.CTkLabel(
            wrapper, text="Publicar nova versão do ORVYN", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            wrapper, text=(
                "1) Gere o manifest.json aqui.  2) Suba o .zip da nova versão e este "
                "manifest.json no Google Drive, ambos com link 'Qualquer pessoa com o link'.  "
                "3) Cole o link do manifest.json no .env de cada instalação (ORVYN_UPDATE_MANIFEST_URL) "
                "— só precisa fazer isso uma vez, por instalação.\n"
                "Veja ATUALIZACOES.txt na raiz do projeto para o passo a passo completo."
            ),
            text_color="gray", justify="left", wraplength=780,
        ).pack(anchor="w", pady=(0, 16))

        ctk.CTkLabel(wrapper, text="Versão (ex.: 1.1.0):").pack(anchor="w")
        self.entry_upd_versao = ctk.CTkEntry(wrapper, placeholder_text="1.1.0", width=200)
        self.entry_upd_versao.pack(anchor="w", pady=(2, 12))

        ctk.CTkLabel(wrapper, text="Link de download direto do .zip (Google Drive):").pack(anchor="w")
        self.entry_upd_url = ctk.CTkEntry(wrapper, placeholder_text="https://drive.google.com/file/d/.../view")
        self.entry_upd_url.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(wrapper, text="Notas da versão:").pack(anchor="w")
        self.texto_upd_notas = ctk.CTkTextbox(wrapper, height=100)
        self.texto_upd_notas.pack(fill="x", pady=(2, 12))

        linha_zip = ctk.CTkFrame(wrapper, fg_color="transparent")
        linha_zip.pack(fill="x", pady=(0, 12))
        self.label_upd_zip = ctk.CTkLabel(linha_zip, text="Nenhum .zip selecionado", text_color="gray")
        self.label_upd_zip.pack(side="left")
        ctk.CTkButton(
            linha_zip, text="Selecionar .zip da versão (calcular SHA-256)...", width=280,
            command=self._selecionar_zip_atualizacao,
        ).pack(side="right")

        self._upd_zip_path = None
        ctk.CTkButton(
            wrapper, text="Gerar manifest.json", width=200, command=self._gerar_manifest
        ).pack(anchor="w")

    def _selecionar_zip_atualizacao(self) -> None:
        caminho = filedialog.askopenfilename(filetypes=[("Arquivo zip", "*.zip")])
        if not caminho:
            return
        self._upd_zip_path = caminho
        self.label_upd_zip.configure(text=os.path.basename(caminho), text_color="white")

    def _gerar_manifest(self) -> None:
        import hashlib
        import json
        versao = self.entry_upd_versao.get().strip()
        url = self.entry_upd_url.get().strip()
        notas = self.texto_upd_notas.get("1.0", "end").strip()
        if not versao or not url:
            messagebox.showerror("Erro", "Preencha a versão e o link de download do .zip.")
            return
        sha256 = ""
        if self._upd_zip_path:
            h = hashlib.sha256()
            with open(self._upd_zip_path, "rb") as f:
                for bloco in iter(lambda: f.read(1 << 20), b""):
                    h.update(bloco)
            sha256 = h.hexdigest()
        manifesto = {"versao": versao, "url_download": url, "sha256": sha256, "notas": notas}
        destino = filedialog.asksaveasfilename(
            defaultextension=".json", initialfile="manifest.json",
            filetypes=[("JSON", "*.json")],
        )
        if not destino:
            return
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(manifesto, f, ensure_ascii=False, indent=2)
        messagebox.showinfo(
            "Manifest gerado",
            f"manifest.json salvo em:\n{destino}\n\n"
            "Agora suba este arquivo e o .zip da versão no Google Drive."
        )

    def _msg_destino_alterado(self, valor: str) -> None:
        if valor == "Uma empresa":
            empresas = EmpresaController.listar_todas()
            self._msg_alvo_por_label = {f"{e.nome} ({e.sigla})": e.id for e in empresas}
        elif valor == "Um usuário":
            usuarios = [u for u in UsuarioController.listar_usuarios() if not u.super_admin]
            self._msg_alvo_por_label = {
                f"{u.nome} — {u.login_completo}": u.id for u in usuarios
            }
        else:
            self._msg_alvo_por_label = {}
            self.combo_msg_alvo.pack_forget()
            return

        rotulos = list(self._msg_alvo_por_label.keys())
        self.combo_msg_alvo.configure(values=rotulos)
        self.combo_msg_alvo.set(rotulos[0] if rotulos else "")
        self.combo_msg_alvo.pack(side="left", padx=(10, 0))

    def _enviar_mensagem(self) -> None:
        rotulo_destino = self.combo_msg_destino.get()
        destino = self._MSG_DESTINOS[rotulo_destino]

        destino_id = None
        if destino in (DESTINO_EMPRESA, DESTINO_USUARIO):
            destino_id = self._msg_alvo_por_label.get(self.combo_msg_alvo.get())
            if destino_id is None:
                messagebox.showwarning("Atenção", "Selecione o destinatário.")
                return

        assunto = self.entry_msg_assunto.get().strip()
        corpo = self.texto_msg_corpo.get("1.0", "end").strip()
        if not assunto or not corpo:
            messagebox.showwarning("Atenção", "Preencha o assunto e a mensagem.")
            return

        try:
            qtd = MensagemController.contar_destinatarios(destino, destino_id)
        except ValueError as e:
            messagebox.showwarning("Atenção", str(e))
            return
        if qtd == 0:
            messagebox.showwarning("Atenção", "Nenhum destinatário com e-mail cadastrado nesse grupo.")
            return
        if not messagebox.askyesno("Confirmar envio", f"Enviar esta mensagem para {qtd} destinatário(s)?"):
            return

        self.botao_msg_enviar.configure(state="disabled", text="Enviando...")
        self.label_msg_status.configure(text=f"Enviando para {qtd} destinatário(s)...")

        def _trabalhar():
            try:
                resultado = MensagemController.enviar(destino, assunto, corpo, destino_id)
            except Exception as e:
                resultado = {"erro": str(e)}
            self.after(0, lambda: self._msg_envio_concluido(resultado))

        threading.Thread(target=_trabalhar, daemon=True).start()

    def _msg_envio_concluido(self, resultado: dict) -> None:
        self.botao_msg_enviar.configure(state="normal", text="Enviar")
        self.label_msg_status.configure(text="")
        if "erro" in resultado:
            messagebox.showerror("Erro", f"Falha ao enviar: {resultado['erro']}")
            return
        texto = f"{resultado['enviados']} e-mail(s) enviado(s)."
        if resultado["sem_email"]:
            texto += f" {resultado['sem_email']} sem e-mail cadastrado."
        if resultado["falhas"]:
            texto += f" {len(resultado['falhas'])} falharam."
        messagebox.showinfo("Envio concluído", texto)


class FormularioAviso(ctk.CTkToplevel):
    """Janela modal para criação de avisos exibidos na tela de login."""

    def __init__(self, master, usuario, ao_salvar):
        super().__init__(master)
        self.usuario = usuario
        self.ao_salvar = ao_salvar
        self.title("Novo Aviso")
        self.geometry("400x420")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(self, text="Novo Aviso", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 15))

        self.entry_titulo = ctk.CTkEntry(self, placeholder_text="Título", width=320)
        self.entry_titulo.pack(pady=8)

        self.texto_mensagem = ctk.CTkTextbox(self, width=320, height=140)
        self.texto_mensagem.pack(pady=8)

        self.entry_expira = ctk.CTkEntry(self, placeholder_text="Expira em (dd/mm/aaaa) - opcional", width=320)
        self.entry_expira.pack(pady=8)

        ctk.CTkButton(self, text="Salvar", width=320, command=self._salvar).pack(pady=20)

    def _salvar(self) -> None:
        try:
            expira_em = None
            texto_expira = self.entry_expira.get().strip()
            if texto_expira:
                expira_em = validar_data(texto_expira).date()
            AvisoController.criar(
                self.entry_titulo.get(), self.texto_mensagem.get("1.0", "end").strip(),
                expira_em, self.usuario.login,
            )
            self.ao_salvar()
            self.destroy()
        except ValidationError as e:
            messagebox.showwarning("Atenção", str(e))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {e}")


class AdminApp(ctk.CTk):
    """Janela raiz do painel administrativo separado (super admin)."""

    def __init__(self):
        super().__init__()
        self.title("ORVYN Master — Painel do Super Admin")
        self.geometry("1100x700")
        self.minsize(950, 600)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.usuario_logado = None
        LoginSuperAdmin(self, ao_autenticar=self._entrar)
        self._agendar_sincronizacao()

    def _agendar_sincronizacao(self) -> None:
        def trabalhar():
            try:
                sincronizar()
            except Exception as e:
                registrar_erro(e, "sincronizacao_automatica_admin_panel")
            finally:
                self.after(60 * 1000, executar_sync)

        def executar_sync():
            threading.Thread(target=trabalhar, daemon=True).start()

        self.after(60 * 1000, executar_sync)

    # --- Atualização automática do próprio Painel Super Admin ---------
    # Usa um manifest.json/versão SEPARADO do app da loja (variável de
    # ambiente ORVYN_MASTER_UPDATE_MANIFEST_URL, ver ATUALIZACOES.txt).
    def _verificar_atualizacao_silenciosa(self) -> None:
        def checar():
            manifesto = atualizador.verificar_atualizacao("ORVYN_MASTER_UPDATE_MANIFEST_URL")
            if manifesto:
                self.after(0, lambda: self._perguntar_atualizacao(manifesto))

        threading.Thread(target=checar, daemon=True).start()

    def _perguntar_atualizacao(self, manifesto: dict) -> None:
        notas = manifesto.get("notas", "")
        if not messagebox.askyesno(
            "Atualização disponível",
            f"Nova versão do ORVYN Master disponível: {manifesto['versao']} "
            f"(atual: {atualizador.versao_atual()}).\n\n{notas}\n\n"
            "Deseja atualizar agora? O painel fecha e reabre sozinho em alguns segundos."
        ):
            return
        try:
            zip_path = atualizador.baixar_atualizacao(manifesto)
            atualizador.aplicar_atualizacao_e_reiniciar(manifesto, zip_path, nome_executavel_win="ORVYN-Master.exe")
        except Exception as e:
            registrar_erro(e, "atualizacao_automatica_admin_panel")
            messagebox.showerror("Erro na atualização", f"Não foi possível atualizar: {e}")

    def _entrar(self, usuario) -> None:
        self.usuario_logado = usuario
        for widget in self.winfo_children():
            widget.destroy()
        PainelSuperAdmin(self, usuario)
        self.after(4000, self._verificar_atualizacao_silenciosa)


def _garantir_super_admin() -> None:
    """
    Garante que o super administrador "aykon" sempre exista neste painel
    master (ALGL mercado.exe, uso exclusivo local, nunca distribuído a
    clientes). Não faz nada se o aykon já existir (não sobrescreve senha
    em uso).
    """
    from database import get_session
    from models import Usuario

    SENHA_AYKON = "****"  # só usado neste painel, que roda apenas na sua máquina

    session = get_session()
    try:
        existe = session.query(Usuario).filter_by(login="aykon", super_admin=True).first()
    finally:
        session.close()
    if existe:
        return

    try:
        UsuarioController.criar_super_admin("Aykon", "aykon", SENHA_AYKON, "aykonlucas63@gmail.com")
    except ValidationError:
        pass  # corrida rara (já criado entre a checagem e aqui); ignora


def main() -> None:
    try:
        init_db()
        _garantir_super_admin()
        registrar_callback_pos_commit_local(sincronizar_em_tempo_real)
        app = AdminApp()
        app.mainloop()
    except Exception as e:
        registrar_erro(e, "admin_panel_main")
        print(f"Erro fatal ao iniciar o painel administrativo: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

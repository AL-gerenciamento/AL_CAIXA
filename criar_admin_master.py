"""
criar_admin_master.py
Script de provisionamento do super administrador da plataforma (Aykon).

Roda uma única vez (ou sempre que precisar redefinir a senha do Aykon).
Não é exposto em nenhuma tela do app principal nem do painel administrativo:
acesso ao super admin só se dá por conhecimento de login/senha, criados aqui.

Uso:
    python criar_admin_master.py

Observação sobre a senha: a leitura é feita com input() comum (a senha
aparece na tela enquanto você digita). Isso é proposital: getpass()
(senha oculta) trava sem aviso em vários terminais do Windows (alguns
Prompt de Comando, atalhos, IDEs). Como este script roda uma única vez,
localmente, por quem já tem acesso à máquina, a senha aparecer na tela
não é um risco relevante.
"""
import sys

from dotenv import load_dotenv
load_dotenv()

from database import init_db, get_session
from models import Usuario
from controllers.usuario_controller import UsuarioController
from utils.validators import ValidationError

LOGIN_MASTER = "aykon"


def _super_admin_existe() -> bool:
    session = get_session()
    try:
        return session.query(Usuario).filter_by(login=LOGIN_MASTER, super_admin=True).first() is not None
    finally:
        session.close()


def _ler_senha_confirmada() -> str:
    while True:
        senha = input("Senha (aparece na tela ao digitar): ")
        confirmacao = input("Confirme a senha: ")
        if senha == confirmacao:
            return senha
        print("As senhas não conferem, tente novamente.\n")


def main() -> None:
    init_db()
    print("=== Provisionamento do super administrador (Aykon) ===")

    if _super_admin_existe():
        print(f"O super administrador '{LOGIN_MASTER}' já existe.")
        resposta = input("Deseja redefinir a senha dele agora? (s/n): ").strip().lower()
        if resposta != "s":
            print("Nada foi alterado.")
            return
        senha = _ler_senha_confirmada()
        try:
            UsuarioController.redefinir_senha_super_admin(LOGIN_MASTER, senha)
            print(f"Senha do super administrador '{LOGIN_MASTER}' redefinida com sucesso.")
        except ValidationError as e:
            print(f"Erro: {e}", file=sys.stderr)
            sys.exit(1)
        return

    nome = input("Nome completo [Aykon]: ").strip() or "Aykon"
    email = input("E-mail: ").strip()
    senha = _ler_senha_confirmada()

    try:
        UsuarioController.criar_super_admin(nome, LOGIN_MASTER, senha, email)
        print(f"Super administrador '{LOGIN_MASTER}' criado com sucesso.")
    except ValidationError as e:
        print(f"Erro: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

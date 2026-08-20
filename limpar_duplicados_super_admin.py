import sys

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from database import init_db, get_session, get_session_cloud, nuvem_disponivel, engine_local, engine_cloud
from controllers.usuario_controller import UsuarioController
from utils.validators import ValidationError
from models import Usuario

LOGIN_MASTER = "aykon"


def _listar(sessao):
    return sessao.query(Usuario).filter_by(login=LOGIN_MASTER, super_admin=True).all()


def _criar_indice_unico(engine, dialeto: str) -> None:
    if engine is None:
        return
    clausula = "super_admin = 1" if dialeto == "sqlite" else "super_admin = true"
    with engine.connect() as conexao:
        conexao.execute(text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_usuario_super_admin_login "
            f"ON usuarios (login) WHERE {clausula}"
        ))
        conexao.commit()


def main() -> None:
    init_db()

    sessao_local = get_session()
    locais = _listar(sessao_local)
    print(f"Registros locais encontrados: {len(locais)}")
    for u in locais:
        print(f"  uuid={u.uuid}  atualizado_em={u.atualizado_em}")

    if len(locais) > 1:
        locais.sort(key=lambda u: u.atualizado_em, reverse=True)
        vencedor, *resto = locais
        print(f"Mantendo local uuid={vencedor.uuid} (mais recente).")
        for u in resto:
            sessao_local.delete(u)
        sessao_local.commit()
    sessao_local.close()

    if nuvem_disponivel():
        sessao_nuvem = get_session_cloud()
        nuvens = _listar(sessao_nuvem)
        print(f"Registros na nuvem encontrados: {len(nuvens)}")
        for u in nuvens:
            print(f"  uuid={u.uuid}  atualizado_em={u.atualizado_em}")

        if len(nuvens) > 1:
            nuvens.sort(key=lambda u: u.atualizado_em, reverse=True)
            vencedor, *resto = nuvens
            print(f"Mantendo na nuvem uuid={vencedor.uuid} (mais recente).")
            for u in resto:
                sessao_nuvem.delete(u)
            sessao_nuvem.commit()
        sessao_nuvem.close()
    else:
        print("Nuvem indisponível; verifique DATABASE_URL para limpar o lado da nuvem também.")

    try:
        _criar_indice_unico(engine_local, "sqlite")
        _criar_indice_unico(engine_cloud, "postgresql")
        print("Índice único de proteção criado/confirmado nos dois bancos.")
    except Exception as e:
        print(f"Aviso: não foi possível criar o índice de proteção: {e}", file=sys.stderr)

    senha = input("Nova senha para o super administrador (deixe em branco para não alterar): ").strip()
    if senha:
        try:
            UsuarioController.redefinir_senha_super_admin(LOGIN_MASTER, senha)
            print("Senha redefinida com sucesso.")
        except ValidationError as e:
            print(f"Erro: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()


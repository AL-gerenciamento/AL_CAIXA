"""
zerar_nuvem.py
Apaga TODOS os dados do banco da NUVEM (Postgres/Supabase), mantendo as
tabelas (estrutura) intactas. O banco LOCAL nunca é tocado por este script.

Uso:
    python zerar_nuvem.py

Por segurança:
- Exige DATABASE_URL configurado no .env (senão o script recusa rodar).
- Mostra quantos registros existem em cada tabela antes de apagar.
- Só executa após você digitar "ZERAR NUVEM" para confirmar.
- Por padrão MANTÉM o super administrador da plataforma (para você não
  ficar sem acesso ao painel). Se quiser apagar também, responda "s"
  quando perguntado.
- Zera o marcador de "última sincronização", para que o próximo ciclo de
  sync trate o banco local como a fonte de verdade e repovoe a nuvem do
  zero a partir dele.
"""
import sys

from dotenv import load_dotenv
load_dotenv()

from database import get_session_cloud, nuvem_disponivel, init_db
from models import (
    Empresa, Usuario, Categoria, Receita, Despesa, DespesaFixa, Meta,
    Pagamento, Aviso, Configuracao, Produto, ItemFichaTecnica, Embalagem,
    Venda, ItemVenda, VendaPagamento, CaixaSaida, MovimentoEstoque, Producao,
)

# Ordem que respeita as dependências de chave estrangeira (filhas antes das
# tabelas que elas referenciam).
TABELAS_EM_ORDEM = [
    ItemVenda, VendaPagamento, Venda, MovimentoEstoque, Producao, CaixaSaida,
    Embalagem, ItemFichaTecnica, Produto,
    Despesa, DespesaFixa, Receita, Categoria, Meta, Aviso, Pagamento,
    Usuario, Empresa,
]

CHAVE_CONFIG_ULTIMA_SYNC = "ultima_sincronizacao"


def main() -> None:
    if not nuvem_disponivel():
        print(
            "Nuvem indisponível ou DATABASE_URL não configurado no .env. "
            "Nada foi apagado."
        )
        sys.exit(1)

    init_db()
    sessao = get_session_cloud()

    print("Registros atuais na nuvem:")
    contagens = {}
    for tabela in TABELAS_EM_ORDEM:
        total = sessao.query(tabela).count()
        contagens[tabela.__tablename__] = total
        print(f"  {tabela.__tablename__:<20} {total}")

    manter_super_admin = input(
        "\nManter o(s) super administrador(es) da plataforma? (S/n): "
    ).strip().lower()
    manter_super_admin = manter_super_admin != "n"

    print(
        "\nATENÇÃO: isso vai apagar definitivamente TODOS os dados acima da "
        "NUVEM. O banco local do seu computador não será alterado."
    )
    confirmacao = input('Digite exatamente "ZERAR NUVEM" para confirmar: ').strip()
    if confirmacao != "ZERAR NUVEM":
        print("Confirmação incorreta. Operação cancelada, nada foi apagado.")
        sessao.close()
        sys.exit(1)

    try:
        for tabela in TABELAS_EM_ORDEM:
            query = sessao.query(tabela)
            if tabela is Usuario and manter_super_admin:
                query = query.filter_by(super_admin=False)
            apagados = query.delete(synchronize_session=False)
            print(f"  {tabela.__tablename__:<20} -{apagados} registro(s) apagado(s)")

        # Zera o marcador de última sincronização (também no lado da
        # nuvem), para o próximo sync repovoar tudo a partir do local.
        cfg = sessao.query(Configuracao).filter_by(chave=CHAVE_CONFIG_ULTIMA_SYNC).first()
        if cfg:
            sessao.delete(cfg)

        sessao.commit()
        print("\nNuvem zerada com sucesso.")
        if manter_super_admin:
            print("Super administrador(es) preservado(s) para você não perder o acesso.")
        print(
            "Lembrete: rode a sincronização (ou abra o app principal) para "
            "repovoar a nuvem com os dados do banco local, se desejar."
        )
    except Exception as e:
        sessao.rollback()
        print(f"Erro ao zerar a nuvem, nada foi alterado: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        sessao.close()


if __name__ == "__main__":
    main()

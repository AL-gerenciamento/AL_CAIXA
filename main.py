"""
main.py
Ponto de entrada do sistema AL Caixa.
Inicializa o banco de dados, popula categorias padrão e inicia a interface.
"""
import os
import sys

from dotenv import load_dotenv
from utils.paths import pasta_base
load_dotenv(os.path.join(pasta_base(), ".env"))  # carrega as variáveis do arquivo .env (ex.: config de SMTP)

from database import init_db
from controllers.categoria_controller import CategoriaController
from controllers.despesa_fixa_controller import DespesaFixaController
from controllers.pagamento_controller import PagamentoController
from utils.logger import registrar_erro


def main() -> None:
    """Inicializa dependências e executa o loop principal da aplicação."""
    try:
        init_db()
        CategoriaController.criar_categorias_padrao()
        DespesaFixaController.gerar_lancamentos_pendentes()
        PagamentoController.gerar_pagamentos_pendentes()
        PagamentoController.verificar_bloqueios()
        PagamentoController.enviar_emails_cobranca()

        from app import App  # importado aqui para garantir que o banco já exista
        app = App()
        app.mainloop()
    except Exception as e:
        registrar_erro(e, "main")
        print(f"Erro fatal ao iniciar a aplicação: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
controllers/estoque_controller.py
Movimentação de estoque: transferências entre Venda / Produção / Prateleira,
reposição, retorno e alertas de estoque baixo/negativo.
"""
from __future__ import annotations

from database import get_session
from models import Produto, MovimentoEstoque
from utils.validators import ValidationError
from utils.logger import registrar_erro, registrar_alteracao

ESTOQUES_VALIDOS = ("venda", "producao", "prateleira")
CAMPO_ESTOQUE = {
    "venda": "estoque_venda",
    "producao": "estoque_producao",
    "prateleira": "estoque_prateleira",
}


class EstoqueController:

    @staticmethod
    def transferir(produto_id: int, origem: str, destino: str, quantidade: float,
                    motivo: str = "", usuario_id: int | None = None, usuario: str = "sistema") -> None:
        session = get_session()
        try:
            if origem not in ESTOQUES_VALIDOS or destino not in ESTOQUES_VALIDOS:
                raise ValidationError("Estoque de origem/destino inválido.")
            if origem == destino:
                raise ValidationError("Origem e destino não podem ser iguais.")
            if quantidade <= 0:
                raise ValidationError("Quantidade deve ser maior que zero.")

            produto = session.get(Produto, produto_id)
            if not produto:
                raise ValidationError("Produto não encontrado.")

            campo_origem = CAMPO_ESTOQUE[origem]
            campo_destino = CAMPO_ESTOQUE[destino]
            disponivel = getattr(produto, campo_origem)
            if disponivel < quantidade:
                raise ValidationError(
                    f"Estoque de {origem} insuficiente ({disponivel:g} disponível) "
                    f"para transferir {quantidade:g}."
                )
            setattr(produto, campo_origem, disponivel - quantidade)
            setattr(produto, campo_destino, getattr(produto, campo_destino) + quantidade)

            session.add(MovimentoEstoque(
                produto_id=produto_id, usuario_id=usuario_id, origem=origem, destino=destino,
                quantidade=quantidade, motivo=motivo or "",
            ))
            session.commit()
            registrar_alteracao(
                usuario, f"Transferência de estoque: {quantidade} de {produto.nome} ({origem} -> {destino})"
            )
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "transferir_estoque")
            raise
        finally:
            session.close()

    @staticmethod
    def entrada(produto_id: int, quantidade: float, motivo: str = "Entrada de estoque",
                destino: str = "venda", usuario_id: int | None = None, usuario: str = "sistema") -> None:
        """Adiciona quantidade ao estoque (compra/reposição), sem descontar de nenhum outro estoque."""
        session = get_session()
        try:
            if destino not in ESTOQUES_VALIDOS:
                raise ValidationError("Estoque de destino inválido.")
            if quantidade <= 0:
                raise ValidationError("Quantidade deve ser maior que zero.")

            produto = session.get(Produto, produto_id)
            if not produto:
                raise ValidationError("Produto não encontrado.")

            campo_destino = CAMPO_ESTOQUE[destino]
            setattr(produto, campo_destino, getattr(produto, campo_destino) + quantidade)

            session.add(MovimentoEstoque(
                produto_id=produto_id, usuario_id=usuario_id, origem="compra", destino=destino,
                quantidade=quantidade, motivo=motivo or "",
            ))
            session.commit()
            registrar_alteracao(
                usuario, f"Entrada de estoque: +{quantidade:g} de {produto.nome} ({motivo})"
            )
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "entrada_estoque")
            raise
        finally:
            session.close()

    @staticmethod
    def repor_prateleira(produto_id: int, quantidade: float, usuario_id: int | None = None,
                          usuario: str = "sistema") -> None:
        """Reposição: move do estoque de venda para a prateleira."""
        EstoqueController.transferir(produto_id, "venda", "prateleira", quantidade,
                                      motivo="Reposição de prateleira", usuario_id=usuario_id, usuario=usuario)

    @staticmethod
    def retornar_ao_estoque(produto_id: int, quantidade: float, usuario_id: int | None = None,
                             usuario: str = "sistema") -> None:
        """Retorno: move da prateleira de volta para o estoque de venda."""
        EstoqueController.transferir(produto_id, "prateleira", "venda", quantidade,
                                      motivo="Retorno ao estoque", usuario_id=usuario_id, usuario=usuario)

    @staticmethod
    def baixar_estoque_venda(session, produto: Produto, quantidade: float) -> bool:
        """
        Desconta do estoque de venda (via prateleira, se houver, senão do estoque geral).
        Retorna True se o estoque ficou insuficiente (negativo).
        """
        if produto.estoque_prateleira >= quantidade:
            produto.estoque_prateleira -= quantidade
        else:
            restante = quantidade - produto.estoque_prateleira
            produto.estoque_prateleira = 0
            produto.estoque_venda -= restante
        return produto.estoque_venda < 0 or produto.estoque_prateleira < 0

    @staticmethod
    def listar_estoque_baixo() -> list[Produto]:
        session = get_session()
        try:
            produtos = session.query(Produto).filter(Produto.ativo == True).all()  # noqa: E712
            baixos = [
                p for p in produtos
                if p.estoque_minimo > 0 and (p.estoque_venda + p.estoque_prateleira) <= p.estoque_minimo
            ]
            session.expunge_all()
            return baixos
        finally:
            session.close()

    @staticmethod
    def listar_estoque_negativo() -> list[Produto]:
        session = get_session()
        try:
            produtos = session.query(Produto).filter(
                (Produto.estoque_venda < 0) | (Produto.estoque_prateleira < 0)
            ).all()
            session.expunge_all()
            return produtos
        finally:
            session.close()

    @staticmethod
    def valor_total_estoque() -> float:
        session = get_session()
        try:
            produtos = session.query(Produto).filter_by(ativo=True).all()
            total = sum(
                (p.estoque_venda + p.estoque_producao + p.estoque_prateleira) * (p.preco_custo or 0)
                for p in produtos
            )
            return round(total, 2)
        finally:
            session.close()

    @staticmethod
    def historico_movimentos(produto_id: int | None = None, limite: int = 100) -> list[MovimentoEstoque]:
        session = get_session()
        try:
            query = session.query(MovimentoEstoque)
            if produto_id:
                query = query.filter_by(produto_id=produto_id)
            movimentos = query.order_by(MovimentoEstoque.data_hora.desc()).limit(limite).all()
            session.expunge_all()
            return movimentos
        finally:
            session.close()

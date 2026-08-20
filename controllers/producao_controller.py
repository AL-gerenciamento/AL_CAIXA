"""
controllers/producao_controller.py
Produção de itens compostos: desconta ingredientes do estoque de produção
e credita o produto final. Também calcula quanto ainda pode ser produzido
com os ingredientes disponíveis (item 13).
"""
from __future__ import annotations

from database import get_session
from models import Produto, ItemFichaTecnica, Producao
from utils.validators import ValidationError
from utils.logger import registrar_erro, registrar_alteracao


class ProducaoController:

    @staticmethod
    def produzir(produto_id: int, quantidade: float, usuario_id: int | None = None,
                  usuario: str = "sistema") -> Producao:
        session = get_session()
        try:
            produto = session.get(Produto, produto_id)
            if not produto or not produto.composto:
                raise ValidationError("Produto não é um item composto (sem ficha técnica).")
            if quantidade <= 0:
                raise ValidationError("Quantidade a produzir deve ser maior que zero.")

            itens = session.query(ItemFichaTecnica).filter_by(produto_id=produto_id).all()
            if not itens:
                raise ValidationError("Produto composto sem ficha técnica cadastrada.")

            custo_total = 0.0
            for item in itens:
                ingrediente = session.get(Produto, item.ingrediente_id)
                necessario = item.quantidade * quantidade
                if ingrediente.estoque_producao < necessario:
                    raise ValidationError(
                        f"Estoque de produção insuficiente de '{ingrediente.nome}' "
                        f"(necessário {necessario}, disponível {ingrediente.estoque_producao})."
                    )
                ingrediente.estoque_producao -= necessario
                custo_total += necessario * (ingrediente.preco_custo or 0.0)

            produto.estoque_venda += quantidade
            producao = Producao(
                produto_id=produto_id, usuario_id=usuario_id,
                quantidade_produzida=quantidade, custo_total=round(custo_total, 2),
            )
            session.add(producao)
            session.commit()
            session.refresh(producao)
            registrar_alteracao(
                usuario, f"Produção: {quantidade}x {produto.nome} (custo R$ {custo_total:.2f})"
            )
            session.expunge(producao)
            return producao
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "produzir")
            raise
        finally:
            session.close()

    @staticmethod
    def quantidade_producivel(produto_id: int) -> float:
        """Quantas unidades ainda podem ser produzidas com os ingredientes disponíveis hoje."""
        session = get_session()
        try:
            produto = session.get(Produto, produto_id)
            if not produto or not produto.composto:
                return 0.0
            itens = session.query(ItemFichaTecnica).filter_by(produto_id=produto_id).all()
            if not itens:
                return 0.0
            limites = []
            for item in itens:
                ingrediente = session.get(Produto, item.ingrediente_id)
                if not ingrediente or item.quantidade <= 0:
                    return 0.0
                limites.append(ingrediente.estoque_producao / item.quantidade)
            return round(min(limites), 2) if limites else 0.0
        finally:
            session.close()

    @staticmethod
    def resumo_producao() -> list[dict]:
        """Para cada produto composto: total já produzido e quanto ainda pode ser produzido."""
        session = get_session()
        try:
            compostos = session.query(Produto).filter_by(composto=True, ativo=True).all()
            resultado = []
            for produto in compostos:
                total_produzido = sum(
                    p.quantidade_produzida
                    for p in session.query(Producao).filter_by(produto_id=produto.id).all()
                )
                resultado.append({
                    "produto": produto.nome,
                    "produto_id": produto.id,
                    "quantidade_produzida_total": total_produzido,
                    "producivel_agora": ProducaoController.quantidade_producivel(produto.id),
                })
            return resultado
        finally:
            session.close()

    @staticmethod
    def historico(produto_id: int | None = None, limite: int = 50) -> list[Producao]:
        session = get_session()
        try:
            query = session.query(Producao)
            if produto_id:
                query = query.filter_by(produto_id=produto_id)
            registros = query.order_by(Producao.data_hora.desc()).limit(limite).all()
            session.expunge_all()
            return registros
        finally:
            session.close()

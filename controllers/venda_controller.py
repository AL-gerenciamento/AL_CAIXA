"""
controllers/venda_controller.py
Registro de vendas: descontar estoque automaticamente, gravar entrada no
caixa e disponibilizar dados para o recibo. Item 2, 3 e 16 da especificação.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func

from database import get_session
from models import Venda, ItemVenda, Produto, VendaPagamento, Usuario
from controllers.estoque_controller import EstoqueController
from controllers.config_controller import ConfigController
from utils.validators import ValidationError
from utils.logger import registrar_erro, registrar_alteracao

DIAS_RETENCAO_HISTORICO = 90


def _validar_desconto_acrescimo(
    desconto_percentual: float, acrescimo_percentual: float, justificativa_acrescimo: str
) -> tuple[float, float, str]:
    """
    Valida desconto/acréscimo contra as margens máximas definidas em
    Configurações (apenas o admin pode alterá-las). Acréscimo sempre exige
    justificativa, visível depois para o admin no histórico de vendas.
    """
    desconto_percentual = max(0.0, float(desconto_percentual or 0))
    acrescimo_percentual = max(0.0, float(acrescimo_percentual or 0))
    justificativa_acrescimo = (justificativa_acrescimo or "").strip()

    limite_desconto = float(ConfigController.obter("desconto_maximo_percentual") or 0)
    limite_acrescimo = float(ConfigController.obter("acrescimo_maximo_percentual") or 0)

    if desconto_percentual > limite_desconto + 0.001:
        raise ValidationError(
            f"Desconto de {desconto_percentual:g}% excede o máximo permitido ({limite_desconto:g}%)."
        )
    if acrescimo_percentual > limite_acrescimo + 0.001:
        raise ValidationError(
            f"Acréscimo de {acrescimo_percentual:g}% excede o máximo permitido ({limite_acrescimo:g}%)."
        )
    if acrescimo_percentual > 0 and not justificativa_acrescimo:
        raise ValidationError("Informe a justificativa do acréscimo.")

    return desconto_percentual, acrescimo_percentual, justificativa_acrescimo


class VendaController:

    @staticmethod
    def _proximo_numero_venda(session, empresa_id: int | None) -> int:
        maior = session.query(func.max(Venda.numero_venda)).filter(
            Venda.empresa_id == empresa_id
        ).scalar()
        return (maior or 0) + 1

    @staticmethod
    def _empresa_do_usuario(session, usuario_id: int | None) -> int | None:
        if usuario_id is None:
            return None
        usuario = session.get(Usuario, usuario_id)
        return usuario.empresa_id if usuario else None

    @staticmethod
    def registrar_venda(itens: list[dict], pagamentos, usuario_id: int | None,
                         usuario: str = "sistema", cliente: str = "",
                         confirmar_estoque_insuficiente: bool = False,
                         desconto_percentual: float = 0.0, acrescimo_percentual: float = 0.0,
                         justificativa_acrescimo: str = "") -> Venda:
        """
        itens: lista de {"produto_id": int, "quantidade": float}
        pagamentos: lista de {"forma_pagamento": str, "valor": float} (permite dividir o
        pagamento em mais de uma forma) ou, por compatibilidade, uma string única com a
        forma de pagamento (nesse caso o valor total é atribuído automaticamente a ela).
        Se algum item ficaria com estoque negativo e confirmar_estoque_insuficiente=False,
        levanta ValidationError com a mensagem para o app perguntar "Deseja continuar a venda?".

        `desconto_percentual`/`acrescimo_percentual` são validados contra as margens máximas
        definidas em Configurações; acréscimo exige `justificativa_acrescimo`.
        """
        session = get_session()
        try:
            if not itens:
                raise ValidationError("Informe ao menos um produto na venda.")

            forma_unica = isinstance(pagamentos, str)
            if forma_unica:
                pagamentos = [{"forma_pagamento": pagamentos, "valor": None}]
            if not pagamentos:
                raise ValidationError("Informe ao menos uma forma de pagamento.")

            desconto_percentual, acrescimo_percentual, justificativa_acrescimo = (
                _validar_desconto_acrescimo(desconto_percentual, acrescimo_percentual, justificativa_acrescimo)
            )

            produtos_cache: dict[int, Produto] = {}
            avisos_estoque = []
            subtotal = 0.0
            for item in itens:
                produto = session.get(Produto, item["produto_id"])
                if not produto:
                    raise ValidationError("Produto não encontrado na venda.")
                if item.get("quantidade", 0) <= 0:
                    raise ValidationError(f"Quantidade inválida para {produto.nome}.")
                disponivel = produto.estoque_venda + produto.estoque_prateleira
                if disponivel < item["quantidade"]:
                    avisos_estoque.append(produto.nome)
                produtos_cache[item["produto_id"]] = produto
                subtotal += round(produto.preco_venda * item["quantidade"], 2)
            subtotal = round(subtotal, 2)
            valor_desconto = round(subtotal * desconto_percentual / 100, 2)
            valor_acrescimo = round(subtotal * acrescimo_percentual / 100, 2)
            valor_total = round(subtotal - valor_desconto + valor_acrescimo, 2)

            if avisos_estoque and not confirmar_estoque_insuficiente:
                raise ValidationError(
                    "Estoque insuficiente para: " + ", ".join(avisos_estoque)
                    + ". Deseja continuar a venda?"
                )

            # Se veio de uma chamada antiga (forma única), preenche o valor com o total.
            if forma_unica:
                pagamentos[0]["valor"] = valor_total
            else:
                soma_pagamentos = round(sum(p["valor"] for p in pagamentos), 2)
                if abs(soma_pagamentos - valor_total) > 0.02:
                    raise ValidationError(
                        f"A soma das formas de pagamento (R$ {soma_pagamentos:.2f}) "
                        f"não bate com o total da venda (R$ {valor_total:.2f})."
                    )

            forma_resumo = (
                pagamentos[0]["forma_pagamento"] if len(pagamentos) == 1
                else "Múltiplas formas"
            )
            empresa_id = VendaController._empresa_do_usuario(session, usuario_id)
            venda = Venda(
                empresa_id=empresa_id,
                numero_venda=VendaController._proximo_numero_venda(session, empresa_id),
                usuario_id=usuario_id, cliente=cliente or "", forma_pagamento=forma_resumo,
                aberta=False, fechada_em=datetime.now(),
                subtotal=subtotal, desconto_percentual=desconto_percentual,
                acrescimo_percentual=acrescimo_percentual, justificativa_acrescimo=justificativa_acrescimo,
            )
            session.add(venda)
            session.flush()

            for pagamento in pagamentos:
                session.add(VendaPagamento(
                    venda_id=venda.id, forma_pagamento=pagamento["forma_pagamento"],
                    valor=round(pagamento["valor"], 2),
                ))

            for item in itens:
                produto = produtos_cache[item["produto_id"]]
                quantidade = item["quantidade"]
                insuficiente = EstoqueController.baixar_estoque_venda(session, produto, quantidade)
                valor_unitario = produto.preco_venda
                valor_item = round(valor_unitario * quantidade, 2)
                session.add(ItemVenda(
                    venda_id=venda.id, produto_id=produto.id, quantidade=quantidade,
                    valor_unitario=valor_unitario, valor_total=valor_item,
                    estoque_insuficiente=insuficiente,
                ))

            venda.valor_total = valor_total
            session.commit()
            session.refresh(venda)
            registrar_alteracao(
                usuario, f"Venda #{venda.numero_venda} registrada - R$ {venda.valor_total:.2f}"
            )
            venda_id = venda.id
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "registrar_venda")
            raise
        finally:
            session.close()
        return VendaController.obter(venda_id)

    @staticmethod
    def obter(venda_id: int) -> Venda | None:
        session = get_session()
        try:
            venda = session.get(Venda, venda_id)
            if venda:
                for item in venda.itens:
                    _ = item.produto.nome
                _ = list(venda.pagamentos)
                session.expunge_all()
            return venda
        finally:
            session.close()

    @staticmethod
    def listar_do_dia(dia=None) -> list[Venda]:
        from datetime import date, datetime, time
        session = get_session()
        try:
            dia = dia or date.today()
            inicio = datetime.combine(dia, time.min)
            fim = datetime.combine(dia, time.max)
            vendas = session.query(Venda).filter(
                Venda.data_hora >= inicio, Venda.data_hora <= fim,
                Venda.cancelada == False, Venda.aberta == False, Venda.deletado == False,  # noqa: E712
            ).order_by(Venda.data_hora.desc()).all()
            session.expunge_all()
            return vendas
        finally:
            session.close()

    @staticmethod
    def salvar_aberta(itens: list[dict], usuario_id: int | None, usuario: str = "sistema",
                       cliente: str = "", venda_id: int | None = None) -> Venda:
        """
        Deixa a venda em aberto (carrinho pendente) para continuar depois, sem travar
        a fila. Não desconta estoque nem exige pagamento; isso só acontece ao fechar
        a venda. Se `venda_id` for informado, atualiza os itens de uma venda em
        aberto já existente em vez de criar outra.
        """
        session = get_session()
        try:
            if not itens:
                raise ValidationError("Informe ao menos um produto na venda.")

            if venda_id:
                venda = session.get(Venda, venda_id)
                if not venda or not venda.aberta:
                    raise ValidationError("Venda em aberto não encontrada.")
                venda.itens.clear()
            else:
                empresa_id = VendaController._empresa_do_usuario(session, usuario_id)
                venda = Venda(
                    empresa_id=empresa_id,
                    numero_venda=VendaController._proximo_numero_venda(session, empresa_id),
                    usuario_id=usuario_id, forma_pagamento="Em aberto", aberta=True,
                )
                session.add(venda)
                session.flush()

            venda.cliente = cliente or ""
            valor_total = 0.0
            for item in itens:
                produto = session.get(Produto, item["produto_id"])
                if not produto:
                    raise ValidationError("Produto não encontrado na venda.")
                if item.get("quantidade", 0) <= 0:
                    raise ValidationError(f"Quantidade inválida para {produto.nome}.")
                valor_item = round(produto.preco_venda * item["quantidade"], 2)
                valor_total += valor_item
                session.add(ItemVenda(
                    venda_id=venda.id, produto_id=produto.id, quantidade=item["quantidade"],
                    valor_unitario=produto.preco_venda, valor_total=valor_item,
                ))
            venda.valor_total = round(valor_total, 2)

            session.commit()
            registrar_alteracao(usuario, f"Venda #{venda.numero_venda} deixada em aberto")
            venda_id = venda.id
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "salvar_venda_aberta")
            raise
        finally:
            session.close()
        return VendaController.obter(venda_id)

    @staticmethod
    def listar_abertas() -> list[Venda]:
        session = get_session()
        try:
            vendas = session.query(Venda).filter_by(
                aberta=True, deletado=False
            ).order_by(Venda.data_hora.desc()).all()
            for venda in vendas:
                for item in venda.itens:
                    _ = item.produto.nome
            session.expunge_all()
            return vendas
        finally:
            session.close()

    @staticmethod
    def descartar_aberta(venda_id: int, usuario: str = "sistema") -> None:
        session = get_session()
        try:
            venda = session.get(Venda, venda_id)
            if not venda or not venda.aberta:
                raise ValidationError("Venda em aberto não encontrada.")
            numero = venda.numero_venda
            venda.deletado = True
            venda.atualizado_em = datetime.now()
            session.commit()
            registrar_alteracao(usuario, f"Venda em aberto #{numero} descartada")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "descartar_venda_aberta")
            raise
        finally:
            session.close()

    @staticmethod
    def fechar_venda(venda_id: int, pagamentos: list[dict], usuario: str = "sistema",
                      confirmar_estoque_insuficiente: bool = False,
                      desconto_percentual: float = 0.0, acrescimo_percentual: float = 0.0,
                      justificativa_acrescimo: str = "") -> Venda:
        """Finaliza uma venda em aberto: valida o pagamento, desconta o estoque e fecha."""
        session = get_session()
        try:
            venda = session.get(Venda, venda_id)
            if not venda or not venda.aberta:
                raise ValidationError("Venda em aberto não encontrada.")
            if not venda.itens:
                raise ValidationError("A venda não tem produtos.")
            if not pagamentos:
                raise ValidationError("Informe ao menos uma forma de pagamento.")

            desconto_percentual, acrescimo_percentual, justificativa_acrescimo = (
                _validar_desconto_acrescimo(desconto_percentual, acrescimo_percentual, justificativa_acrescimo)
            )
            subtotal = venda.valor_total  # em aberto, valor_total ainda é a soma bruta dos itens
            valor_desconto = round(subtotal * desconto_percentual / 100, 2)
            valor_acrescimo = round(subtotal * acrescimo_percentual / 100, 2)
            valor_total_final = round(subtotal - valor_desconto + valor_acrescimo, 2)

            soma_pagamentos = round(sum(p["valor"] for p in pagamentos), 2)
            if abs(soma_pagamentos - valor_total_final) > 0.02:
                raise ValidationError(
                    f"A soma das formas de pagamento (R$ {soma_pagamentos:.2f}) "
                    f"não bate com o total da venda (R$ {valor_total_final:.2f})."
                )

            avisos_estoque = []
            for item in venda.itens:
                produto = item.produto
                disponivel = produto.estoque_venda + produto.estoque_prateleira
                if disponivel < item.quantidade:
                    avisos_estoque.append(produto.nome)
            if avisos_estoque and not confirmar_estoque_insuficiente:
                raise ValidationError(
                    "Estoque insuficiente para: " + ", ".join(avisos_estoque)
                    + ". Deseja continuar a venda?"
                )

            for item in venda.itens:
                item.estoque_insuficiente = EstoqueController.baixar_estoque_venda(
                    session, item.produto, item.quantidade
                )

            for pagamento in pagamentos:
                session.add(VendaPagamento(
                    venda_id=venda.id, forma_pagamento=pagamento["forma_pagamento"],
                    valor=round(pagamento["valor"], 2),
                ))

            venda.forma_pagamento = (
                pagamentos[0]["forma_pagamento"] if len(pagamentos) == 1 else "Múltiplas formas"
            )
            venda.subtotal = subtotal
            venda.desconto_percentual = desconto_percentual
            venda.acrescimo_percentual = acrescimo_percentual
            venda.justificativa_acrescimo = justificativa_acrescimo
            venda.valor_total = valor_total_final
            venda.aberta = False
            venda.fechada_em = datetime.now()
            session.commit()
            registrar_alteracao(usuario, f"Venda #{venda.numero_venda} fechada - R$ {venda.valor_total:.2f}")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "fechar_venda")
            raise
        finally:
            session.close()
        return VendaController.obter(venda_id)

    @staticmethod
    def listar_historico(limite: int = 300) -> list[Venda]:
        """Vendas já fechadas (finalizadas ou canceladas), mais recentes primeiro."""
        session = get_session()
        try:
            vendas = (
                session.query(Venda).filter_by(aberta=False, deletado=False)
                .order_by(Venda.data_hora.desc()).limit(limite).all()
            )
            session.expunge_all()
            return vendas
        finally:
            session.close()

    @staticmethod
    def limpar_historico_antigo(dias: int = DIAS_RETENCAO_HISTORICO) -> int:
        """
        Oculta (soft-delete) vendas já fechadas há mais de `dias` dias, para
        não acumular histórico indefinidamente na tela. Vendas em aberto
        nunca são apagadas por aqui.

        Usa soft-delete (campo `deletado`), igual às outras tabelas
        sincronizáveis, em vez de apagar a linha de fato: como a venda já
        foi copiada para a nuvem pelo sync, um hard-delete local faria o
        próximo ciclo de sincronização trazer a venda de volta do lado da
        nuvem (reg_local ausente + reg_nuvem presente = cópia de volta).
        """
        session = get_session()
        try:
            limite = datetime.now() - timedelta(days=dias)
            antigas = session.query(Venda).filter(
                Venda.aberta == False, Venda.fechada_em.isnot(None),  # noqa: E712
                Venda.fechada_em < limite, Venda.deletado == False,  # noqa: E712
            ).all()
            quantidade = len(antigas)
            agora = datetime.now()
            for venda in antigas:
                venda.deletado = True
                venda.atualizado_em = agora
            if quantidade:
                session.commit()
                registrar_alteracao(
                    "sistema", f"{quantidade} venda(s) com mais de {dias} dias removidas do histórico"
                )
            return quantidade
        except Exception as e:
            session.rollback()
            registrar_erro(e, "limpar_historico_antigo")
            return 0
        finally:
            session.close()

    @staticmethod
    def produtos_mais_vendidos(limite: int = 10) -> list[dict]:
        session = get_session()
        try:
            resultados = (
                session.query(
                    Produto.nome, func.sum(ItemVenda.quantidade).label("qtd"),
                    func.sum(ItemVenda.valor_total).label("total"),
                )
                .join(Produto, Produto.id == ItemVenda.produto_id)
                .join(Venda, Venda.id == ItemVenda.venda_id)
                .filter(Venda.cancelada == False, Venda.aberta == False, Venda.deletado == False)  # noqa: E712
                .group_by(Produto.id)
                .order_by(func.sum(ItemVenda.quantidade).desc())
                .limit(limite)
                .all()
            )
            return [{"nome": r[0], "quantidade": r[1], "total": round(r[2], 2)} for r in resultados]
        finally:
            session.close()

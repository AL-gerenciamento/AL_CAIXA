"""
controllers/produto_controller.py
Cadastro de produtos, ficha técnica (produtos compostos), embalagens
e cálculo automático de custo/preço/margem.
"""
from __future__ import annotations

from sqlalchemy import func

from database import get_session
from models import Produto, ItemFichaTecnica, Embalagem
from utils.validators import validar_texto_obrigatorio, ValidationError
from utils.logger import registrar_erro, registrar_alteracao


class ProdutoController:

    @staticmethod
    def _proximo_codigo_interno(session, empresa_id: int | None) -> int:
        maior = session.query(func.max(Produto.codigo_interno)).filter(
            Produto.empresa_id == empresa_id
        ).scalar()
        return (maior or 0) + 1

    @staticmethod
    def listar(apenas_ativos: bool = True, termo: str = "") -> list[Produto]:
        session = get_session()
        try:
            query = session.query(Produto)
            if apenas_ativos:
                query = query.filter_by(ativo=True)
            if termo:
                termo_like = f"%{termo}%"
                query = query.filter(
                    (Produto.nome.ilike(termo_like))
                    | (Produto.codigo_barras.ilike(termo_like))
                    | (Produto.codigo_sku.ilike(termo_like))
                )
            produtos = query.order_by(Produto.codigo_interno).all()
            session.expunge_all()
            return produtos
        finally:
            session.close()

    @staticmethod
    def buscar_por_codigo(codigo: str) -> Produto | None:
        """Busca por código de barras, código interno ou SKU (usado na leitura por leitor/scanner)."""
        session = get_session()
        try:
            codigo = (codigo or "").strip()
            produto = session.query(Produto).filter_by(codigo_barras=codigo).first()
            if not produto:
                produto = session.query(Produto).filter_by(codigo_sku=codigo).first()
            if not produto and codigo.isdigit():
                produto = session.query(Produto).filter_by(codigo_interno=int(codigo)).first()
            if produto:
                session.expunge(produto)
            return produto
        finally:
            session.close()

    @staticmethod
    def obter(produto_id: int) -> Produto | None:
        session = get_session()
        try:
            produto = session.get(Produto, produto_id)
            if produto:
                session.expunge(produto)
            return produto
        finally:
            session.close()

    @staticmethod
    def criar(nome: str, categoria: str = "", codigo_barras: str = "", codigo_sku: str = "",
               unidade_medida: str = "un", preco_custo: float = 0.0, preco_venda: float = 0.0,
               estoque_venda: float = 0.0, estoque_minimo: float = 0.0, composto: bool = False,
               usuario: str = "sistema", empresa_id: int | None = None) -> Produto:
        session = get_session()
        try:
            nome = validar_texto_obrigatorio(nome, "Nome do produto", 150)
            if preco_venda < 0 or preco_custo < 0:
                raise ValidationError("Preços não podem ser negativos.")

            codigo_barras = (codigo_barras or "").strip() or None
            codigo_sku = (codigo_sku or "").strip() or None
            if codigo_barras and session.query(Produto).filter_by(
                codigo_barras=codigo_barras, empresa_id=empresa_id
            ).first():
                raise ValidationError("Já existe um produto com este código de barras.")
            if codigo_sku and session.query(Produto).filter_by(
                codigo_sku=codigo_sku, empresa_id=empresa_id
            ).first():
                raise ValidationError("Já existe um produto com este código/SKU.")

            produto = Produto(
                empresa_id=empresa_id,
                codigo_interno=ProdutoController._proximo_codigo_interno(session, empresa_id),
                nome=nome, categoria=(categoria or "").strip(),
                codigo_barras=codigo_barras, codigo_sku=codigo_sku,
                unidade_medida=unidade_medida or "un",
                preco_custo=round(preco_custo, 2), preco_venda=round(preco_venda, 2),
                estoque_venda=estoque_venda, estoque_minimo=estoque_minimo,
                composto=composto,
            )
            ProdutoController._recalcular_margem(produto)
            session.add(produto)
            session.commit()
            session.refresh(produto)
            registrar_alteracao(usuario, f"Produto cadastrado: {produto.codigo_interno} - {nome}")
            session.expunge(produto)
            return produto
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "criar_produto")
            raise
        finally:
            session.close()

    @staticmethod
    def editar(produto_id: int, usuario: str = "sistema", **campos) -> None:
        session = get_session()
        try:
            produto = session.get(Produto, produto_id)
            if not produto:
                raise ValidationError("Produto não encontrado.")
            if "nome" in campos:
                produto.nome = validar_texto_obrigatorio(campos["nome"], "Nome do produto", 150)
            for campo in ("codigo_barras", "codigo_sku"):
                if campo in campos:
                    valor = (campos[campo] or "").strip() or None
                    setattr(produto, campo, valor)
            for campo in ("categoria", "unidade_medida"):
                if campo in campos:
                    setattr(produto, campo, (campos[campo] or "").strip())
            for campo in ("preco_custo", "preco_venda", "estoque_minimo"):
                if campo in campos and campos[campo] is not None:
                    setattr(produto, campo, round(float(campos[campo]), 2))
            ProdutoController._recalcular_margem(produto)
            session.commit()
            registrar_alteracao(usuario, f"Produto editado: {produto.codigo_interno} - {produto.nome}")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "editar_produto")
            raise
        finally:
            session.close()

    @staticmethod
    def inativar(produto_id: int, usuario: str = "sistema") -> None:
        session = get_session()
        try:
            produto = session.get(Produto, produto_id)
            if produto:
                produto.ativo = False
                session.commit()
                registrar_alteracao(usuario, f"Produto inativado: {produto.codigo_interno} - {produto.nome}")
        except Exception as e:
            session.rollback()
            registrar_erro(e, "inativar_produto")
            raise
        finally:
            session.close()

    # --- Ficha técnica (receita de produtos compostos) ---

    @staticmethod
    def definir_ficha_tecnica(produto_id: int, ingredientes: list[dict], usuario: str = "sistema") -> None:
        """
        ingredientes: lista de {"ingrediente_id": int, "quantidade": float,
                                 "unidade_medida": str, "observacoes": str}
        Substitui a ficha técnica completa do produto.
        """
        session = get_session()
        try:
            produto = session.get(Produto, produto_id)
            if not produto:
                raise ValidationError("Produto não encontrado.")
            if produto_id in [i["ingrediente_id"] for i in ingredientes]:
                raise ValidationError("Um produto não pode ser ingrediente de si mesmo.")

            session.query(ItemFichaTecnica).filter_by(produto_id=produto_id).delete()
            for item in ingredientes:
                if not item.get("ingrediente_id") or float(item.get("quantidade", 0)) <= 0:
                    raise ValidationError("Ingrediente e quantidade são obrigatórios.")
                session.add(ItemFichaTecnica(
                    produto_id=produto_id,
                    ingrediente_id=item["ingrediente_id"],
                    quantidade=float(item["quantidade"]),
                    unidade_medida=item.get("unidade_medida", "un"),
                    observacoes=item.get("observacoes", ""),
                ))
            produto.composto = True
            ProdutoController._recalcular_custo_composto(session, produto)
            session.commit()
            registrar_alteracao(usuario, f"Ficha técnica atualizada: {produto.nome}")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "definir_ficha_tecnica")
            raise
        finally:
            session.close()

    @staticmethod
    def obter_ficha_tecnica(produto_id: int) -> list[ItemFichaTecnica]:
        session = get_session()
        try:
            itens = session.query(ItemFichaTecnica).filter_by(produto_id=produto_id).all()
            session.expunge_all()
            return itens
        finally:
            session.close()

    @staticmethod
    def _recalcular_custo_composto(session, produto: Produto) -> None:
        """Custo da matéria-prima = soma (qtd ingrediente * custo unitário do ingrediente)."""
        itens = session.query(ItemFichaTecnica).filter_by(produto_id=produto.id).all()
        custo_total = 0.0
        for item in itens:
            ingrediente = session.get(Produto, item.ingrediente_id)
            if ingrediente:
                custo_total += item.quantidade * (ingrediente.preco_custo or 0.0)
        produto.preco_custo = round(custo_total, 2)
        ProdutoController._recalcular_margem(produto)

    @staticmethod
    def _recalcular_margem(produto: Produto) -> None:
        if produto.preco_custo and produto.preco_custo > 0:
            produto.margem_lucro = round(
                ((produto.preco_venda - produto.preco_custo) / produto.preco_custo) * 100, 2
            )
        else:
            produto.margem_lucro = 0.0

    @staticmethod
    def definir_preco_por_margem(produto_id: int, margem_percentual: float, usuario: str = "sistema") -> Produto:
        """Calcula preco_venda a partir do custo + margem de lucro desejada."""
        session = get_session()
        try:
            produto = session.get(Produto, produto_id)
            if not produto:
                raise ValidationError("Produto não encontrado.")
            produto.preco_venda = round(produto.preco_custo * (1 + margem_percentual / 100), 2)
            produto.margem_lucro = round(margem_percentual, 2)
            session.commit()
            session.refresh(produto)
            registrar_alteracao(usuario, f"Preço recalculado por margem: {produto.nome}")
            session.expunge(produto)
            return produto
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "definir_preco_por_margem")
            raise
        finally:
            session.close()

    @staticmethod
    def resumo_custos(produto_id: int) -> dict:
        session = get_session()
        try:
            produto = session.get(Produto, produto_id)
            if not produto:
                raise ValidationError("Produto não encontrado.")
            lucro_bruto = round(produto.preco_venda - produto.preco_custo, 2)
            return {
                "custo_materia_prima": produto.preco_custo,
                "custo_total": produto.preco_custo,
                "preco_venda": produto.preco_venda,
                "lucro_bruto": lucro_bruto,
                "percentual_lucro": produto.margem_lucro,
            }
        finally:
            session.close()

    # --- Embalagens / caixas ---

    @staticmethod
    def adicionar_embalagem(produto_id: int, codigo_caixa: str, qtd_unidades_por_caixa: float,
                              valor_caixa: float, codigo_unidade: str = "", valor_unidade: float = 0.0,
                              usuario: str = "sistema") -> Embalagem:
        session = get_session()
        try:
            if not session.get(Produto, produto_id):
                raise ValidationError("Produto não encontrado.")
            if qtd_unidades_por_caixa <= 0:
                raise ValidationError("Quantidade de unidades por caixa deve ser maior que zero.")
            embalagem = Embalagem(
                produto_id=produto_id, codigo_caixa=(codigo_caixa or "").strip() or None,
                qtd_unidades_por_caixa=qtd_unidades_por_caixa, valor_caixa=round(valor_caixa, 2),
                codigo_unidade=(codigo_unidade or "").strip() or None, valor_unidade=round(valor_unidade, 2),
            )
            session.add(embalagem)
            session.commit()
            session.refresh(embalagem)
            registrar_alteracao(usuario, f"Embalagem cadastrada para produto {produto_id}")
            session.expunge(embalagem)
            return embalagem
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "adicionar_embalagem")
            raise
        finally:
            session.close()

    @staticmethod
    def entrada_caixas(embalagem_id: int, qtd_caixas: float, usuario: str = "sistema") -> None:
        """Dá entrada em caixas fechadas e converte automaticamente em estoque de unidades."""
        session = get_session()
        try:
            embalagem = session.get(Embalagem, embalagem_id)
            if not embalagem:
                raise ValidationError("Embalagem não encontrada.")
            if qtd_caixas <= 0:
                raise ValidationError("Quantidade de caixas deve ser maior que zero.")
            embalagem.estoque_caixas += qtd_caixas
            embalagem.estoque_unidades += qtd_caixas * embalagem.qtd_unidades_por_caixa
            produto = session.get(Produto, embalagem.produto_id)
            if produto:
                produto.estoque_venda += qtd_caixas * embalagem.qtd_unidades_por_caixa
            session.commit()
            registrar_alteracao(usuario, f"Entrada de {qtd_caixas} caixa(s) na embalagem {embalagem_id}")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "entrada_caixas")
            raise
        finally:
            session.close()

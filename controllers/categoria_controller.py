"""
controllers/categoria_controller.py
Regras de negócio para categorias de receitas/despesas.
"""
from __future__ import annotations

from database import get_session
from models import Categoria
from utils.validators import validar_texto_obrigatorio, ValidationError
from utils.logger import registrar_erro, registrar_alteracao

CATEGORIAS_PADRAO = [
    # Despesas
    ("Folha de Pagamento", "despesa", "#E67E22"),
    ("Fornecedores", "despesa", "#3498DB"),
    ("Aluguel", "despesa", "#7F8C8D"),
    ("Impostos e Taxas", "despesa", "#E74C3C"),
    ("Marketing e Publicidade", "despesa", "#9B59B6"),
    ("Serviços de Terceiros", "despesa", "#D35400"),
    ("Equipamentos e Materiais", "despesa", "#34495E"),
    ("Software e Assinaturas", "despesa", "#8E44AD"),
    ("Manutenção", "despesa", "#C0392B"),
    ("Outros", "despesa", "#95A5A6"),
    # Receitas
    ("Vendas", "receita", "#2ECC71"),
    ("Prestação de Serviços", "receita", "#27AE60"),
    ("Investimentos", "receita", "#16A085"),
    ("Outros", "receita", "#1ABC9C"),
]


class CategoriaController:
    """CRUD de categorias."""

    @staticmethod
    def criar_categorias_padrao() -> None:
        """Popula o banco com categorias padrão na primeira execução."""
        session = get_session()
        try:
            if session.query(Categoria).count() > 0:
                return
            for nome, tipo, cor in CATEGORIAS_PADRAO:
                session.add(Categoria(nome=nome, tipo=tipo, cor=cor))
            session.commit()
        except Exception as e:
            session.rollback()
            registrar_erro(e, "criar_categorias_padrao")
        finally:
            session.close()

    @staticmethod
    def listar(tipo: str | None = None) -> list[Categoria]:
        session = get_session()
        try:
            query = session.query(Categoria)
            if tipo:
                query = query.filter_by(tipo=tipo)
            categorias = query.order_by(Categoria.nome).all()
            session.expunge_all()
            return categorias
        finally:
            session.close()

    @staticmethod
    def criar(nome: str, tipo: str, cor: str = "#3B8ED0") -> Categoria:
        session = get_session()
        try:
            nome = validar_texto_obrigatorio(nome, "Nome da categoria", 60)
            if tipo not in ("receita", "despesa"):
                raise ValidationError("Tipo de categoria inválido.")
            if session.query(Categoria).filter_by(nome=nome, tipo=tipo).first():
                raise ValidationError("Já existe uma categoria com este nome e tipo.")
            categoria = Categoria(nome=nome, tipo=tipo, cor=cor)
            session.add(categoria)
            session.commit()
            session.refresh(categoria)
            registrar_alteracao("sistema", f"Categoria criada: {nome} ({tipo})")
            return categoria
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "criar_categoria")
            raise
        finally:
            session.close()

    @staticmethod
    def editar(categoria_id: int, nome: str, cor: str) -> None:
        session = get_session()
        try:
            categoria = session.get(Categoria, categoria_id)
            if not categoria:
                raise ValidationError("Categoria não encontrada.")
            categoria.nome = validar_texto_obrigatorio(nome, "Nome da categoria", 60)
            categoria.cor = cor
            session.commit()
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "editar_categoria")
            raise
        finally:
            session.close()

    @staticmethod
    def excluir(categoria_id: int) -> None:
        session = get_session()
        try:
            categoria = session.get(Categoria, categoria_id)
            if categoria:
                if categoria.receitas or categoria.despesas:
                    raise ValidationError(
                        "Não é possível excluir: existem lançamentos vinculados a esta categoria."
                    )
                session.delete(categoria)
                session.commit()
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "excluir_categoria")
            raise
        finally:
            session.close()

"""
models.py
Definição de todas as tabelas do banco de dados via SQLAlchemy ORM.
"""
from __future__ import annotations

import enum
import uuid as uuid_lib
from datetime import datetime, date

from sqlalchemy import (
    String, Integer, Float, Date, DateTime, Boolean, ForeignKey, Enum, UniqueConstraint, Index, text, event
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, Session
)

from utils.device import obter_device_id


class Base(DeclarativeBase):
    """Classe base declarativa para todos os modelos."""
    pass


class SyncMixin:
    """
    Mixin aplicado a toda tabela que participa da sincronização local <-> nuvem.

    - uuid: identificador global estável, igual nos dois bancos (não muda,
      diferente do "id" que é autoincremento local a cada banco). Faz o
      papel do "id UUID PRIMARY KEY" da arquitetura de sincronização.
    - criado_em: data de criação do registro (equivalente a "created_at").
    - atualizado_em: usado para decidir, durante o merge automático, qual
      versão é mais recente. Atualizado a cada alteração do registro
      (equivalente a "updated_at").
    - device_id: computador/instalação que gravou a última alteração (ver
      utils/device.py). Preenchido automaticamente pelo listener abaixo.
    - sync_version: contador incrementado a cada alteração do registro,
      usado como controle de versão adicional ao lado de atualizado_em.
    - deletado: soft-delete. Registros nunca são apagados de fato durante o
      sync (evita reaparecer um registro apagado só de um lado); ficam
      marcados e ocultos da aplicação (equivalente a "deleted_at").
    """
    uuid: Mapped[str] = mapped_column(
        String(36), default=lambda: str(uuid_lib.uuid4()), unique=True, nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    device_id: Mapped[str] = mapped_column(String(40), default=obter_device_id, nullable=True)
    sync_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    deletado: Mapped[bool] = mapped_column(Boolean, default=False)


class Permissao(str, enum.Enum):
    ADMIN = "Administrador"
    USUARIO = "Usuario"


# Módulos que podem ser liberados individualmente para um sub-usuário
# (permissao=Usuario). Administradores e o super admin sempre têm acesso
# total, independente desta lista. Dashboard, Central de Ajuda e
# Administração não entram aqui: os dois primeiros são sempre liberados
# e o último é exclusivo de Administrador.
MODULOS_PERMISSAO = [
    "Caixa / Venda",
    "Histórico de Vendas",
    "Produtos",
    "Estoque e Produção",
    "Receitas",
    "Despesas",
    "Categorias",
    "Metas Financeiras",
    "Relatórios",
    "Configurações",
]


class TipoPessoa(str, enum.Enum):
    FISICA = "Pessoa Física"
    JURIDICA = "Pessoa Jurídica"


class Empresa(SyncMixin, Base):
    """
    Empresa/conta cadastrada no sistema (tenant). Agrupa todos os usuários
    vinculados a ela. Nome e sigla são definidos uma única vez no cadastro
    e não podem ser alterados depois (imutáveis por regra de negócio,
    aplicada em EmpresaController). A sigla é usada no login de todo
    usuário vinculado, no formato "usuario@SIGLA".
    """
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    sigla: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    tipo_pessoa: Mapped[TipoPessoa] = mapped_column(Enum(TipoPessoa), nullable=False)

    # --- Pessoa Física ---
    nome_completo: Mapped[str] = mapped_column(String(150), nullable=True)
    cpf: Mapped[str] = mapped_column(String(11), unique=True, nullable=True)
    data_nascimento: Mapped[date] = mapped_column(Date, nullable=True)

    # --- Pessoa Jurídica ---
    razao_social: Mapped[str] = mapped_column(String(150), nullable=True)
    nome_fantasia: Mapped[str] = mapped_column(String(150), nullable=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    logo_path: Mapped[str] = mapped_column(String(300), nullable=True)

    # --- Controle de acesso à nuvem pelo super admin (independente do
    # bloqueio de login por mensalidade em atraso). Quando False, o app
    # desta empresa continua funcionando 100% local, mas para de
    # sincronizar/enxergar a nuvem até o super admin reativar. ---
    nuvem_liberada: Mapped[bool] = mapped_column(Boolean, default=True)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="empresa")


class Usuario(SyncMixin, Base):
    """
    Usuários do sistema, com senha criptografada e nível de permissão.

    Multi-empresa:
    - Todo usuário (exceto o super administrador da plataforma) pertence
      a uma Empresa (empresa_id). O login é único apenas dentro da mesma
      empresa (UniqueConstraint abaixo); o identificador completo exibido
      e usado para autenticar é "login@SIGLA_DA_EMPRESA".

    Hierarquia dentro da empresa:
    - O usuário que cadastra a empresa é sempre o admin "conta principal"
      dela (criado_por_id = None, conta_principal_id = None) e é criado
      automaticamente como Administrador.
    - Todo usuário criado por um admin já existente é um "sub-usuário":
      fica vinculado à mesma conta principal (conta_principal_id aponta
      para o id do admin raiz), mesmo que ele próprio seja Administrador.
      criado_por_id sempre indica quem especificamente o criou.
    - Cobrança e bloqueio em massa são feitos por conta_principal_id
      (toda a "família" de uma conta principal, dentro da empresa).

    Super administrador da plataforma:
    - Um único usuário especial (super_admin = True) não pertence a
      nenhuma empresa (empresa_id = None) e enxerga o sistema inteiro.
      É criado apenas via provisionamento (ver criar_admin_master.py) e
      acessa exclusivamente o painel administrativo separado (admin_panel/app.py).
    """
    __tablename__ = "usuarios"
    __table_args__ = (
        UniqueConstraint("empresa_id", "login", name="uq_usuario_login_empresa"),
        Index(
            "uq_usuario_super_admin_login", "login", unique=True,
            sqlite_where=text("super_admin = 1"),
            postgresql_where=text("super_admin = true"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    login: Mapped[str] = mapped_column(String(60), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    permissao: Mapped[Permissao] = mapped_column(
        Enum(Permissao), default=Permissao.USUARIO, nullable=False
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # --- Vínculo com a empresa (tenant); None apenas para o super admin ---
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=True)
    empresa: Mapped["Empresa"] = relationship(back_populates="usuarios")

    # --- Super administrador da plataforma (ex.: Aykon) ---
    super_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # Campos usados no fluxo de "esqueci minha senha" (código enviado por e-mail)
    reset_token: Mapped[str] = mapped_column(String(6), nullable=True)
    reset_token_expira: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # --- Hierarquia (admin / sub-usuário) dentro da mesma empresa ---
    criado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    conta_principal_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=True)

    # --- Verificação de e-mail no cadastro ---
    email_verificado: Mapped[bool] = mapped_column(Boolean, default=False)
    codigo_verificacao: Mapped[str] = mapped_column(String(6), nullable=True)
    codigo_verificacao_expira: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # --- Bloqueio (manual pelo admin ou automático por falta de pagamento) ---
    bloqueado: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_bloqueio: Mapped[str] = mapped_column(String(200), nullable=True)

    # --- Permissões granulares (só valem para permissao=Usuario) ---
    permissoes_modulos: Mapped[str] = mapped_column(String(500), default="", nullable=True)

    @property
    def login_completo(self) -> str:
        """Retorna 'usuario@SIGLA', ou apenas o login para o super admin (sem empresa)."""
        if self.empresa is not None:
            return f"{self.login}@{self.empresa.sigla}"
        return self.login

    def tem_permissao(self, modulo: str) -> bool:
        """Diz se o usuário pode acessar o módulo/tela informado.

        Administradores e o super admin sempre têm acesso total. Dashboard
        e Central de Ajuda são sempre liberados. Administração é exclusivo
        de Administrador. Para os demais módulos, um sub-usuário (Usuario)
        só acessa o que estiver na sua lista `permissoes_modulos`.
        """
        if self.super_admin or self.permissao == Permissao.ADMIN:
            return True
        if modulo in ("Dashboard", "Central de Ajuda"):
            return True
        if modulo == "Administração":
            return False
        liberados = (self.permissoes_modulos or "").split(",")
        return modulo in liberados


class Categoria(SyncMixin, Base):
    """Categorias de receitas/despesas (ex.: Alimentação, Transporte)."""
    __tablename__ = "categorias"
    __table_args__ = (UniqueConstraint("nome", "tipo", name="uq_categoria_nome_tipo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(60), nullable=False)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)  # "receita" ou "despesa"
    cor: Mapped[str] = mapped_column(String(7), default="#3B8ED0")  # cor hex p/ gráficos

    receitas: Mapped[list["Receita"]] = relationship(back_populates="categoria")
    despesas: Mapped[list["Despesa"]] = relationship(back_populates="categoria")


class Receita(SyncMixin, Base):
    """Lançamentos de receitas."""
    __tablename__ = "receitas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    observacoes: Mapped[str] = mapped_column(String(500), default="")
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=True)

    categoria: Mapped["Categoria"] = relationship(back_populates="receitas")


class Despesa(SyncMixin, Base):
    """Lançamentos de despesas, com status pago/pendente."""
    __tablename__ = "despesas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    observacoes: Mapped[str] = mapped_column(String(500), default="")
    paga: Mapped[bool] = mapped_column(Boolean, default=False)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=True)

    # Se não-nulo, indica que este lançamento foi gerado automaticamente
    # a partir de uma despesa fixa (diária/semanal/mensal/boleto)
    despesa_fixa_id: Mapped[int] = mapped_column(ForeignKey("despesas_fixas.id"), nullable=True)

    categoria: Mapped["Categoria"] = relationship(back_populates="despesas")
    despesa_fixa: Mapped["DespesaFixa"] = relationship(back_populates="lancamentos")


class DespesaFixa(SyncMixin, Base):
    """
    Molde de uma despesa recorrente (diária, semanal, mensal ou boleto).
    A cada início do sistema, os lançamentos pendentes são gerados
    automaticamente na tabela Despesa, conforme a recorrência configurada.
    """
    __tablename__ = "despesas_fixas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    observacoes: Mapped[str] = mapped_column(String(500), default="")
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))

    # "diaria" | "semanal" | "mensal" | "boleto"
    tipo_recorrencia: Mapped[str] = mapped_column(String(10), nullable=False)
    # Usado quando tipo_recorrencia == "semanal": 0=segunda ... 6=domingo
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=True)
    # Usado quando tipo_recorrencia in ("mensal", "boleto"): dia do mês (1-31)
    dia_mes: Mapped[int] = mapped_column(Integer, nullable=True)

    data_inicio: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    data_fim: Mapped[date] = mapped_column(Date, nullable=True)  # opcional: quando parar de gerar
    ultima_geracao: Mapped[date] = mapped_column(Date, nullable=True)  # controle interno

    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    categoria: Mapped["Categoria"] = relationship()
    lancamentos: Mapped[list["Despesa"]] = relationship(back_populates="despesa_fixa")


class Meta(SyncMixin, Base):
    """Metas financeiras com valor alvo, prazo e progresso."""
    __tablename__ = "metas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String(150), nullable=False)
    valor_alvo: Mapped[float] = mapped_column(Float, nullable=False)
    valor_atual: Mapped[float] = mapped_column(Float, default=0.0)
    prazo: Mapped[date] = mapped_column(Date, nullable=False)
    concluida: Mapped[bool] = mapped_column(Boolean, default=False)


class StatusPagamento(str, enum.Enum):
    PENDENTE = "Pendente"
    PAGO = "Pago"
    ATRASADO = "Atrasado"


class Pagamento(SyncMixin, Base):
    """
    Mensalidade de uma conta principal (admin + seus sub-usuários).
    Gerada automaticamente todo mês com vencimento no dia 5 (ou no próximo
    dia útil, caso caia em fim de semana ou feriado nacional). Se o admin
    não marcar como pago em até 3 dias úteis após o vencimento, o sistema
    bloqueia automaticamente a conta.
    """
    __tablename__ = "pagamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conta_principal_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    referencia: Mapped[str] = mapped_column(String(7), nullable=False)  # "AAAA-MM"
    vencimento: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[StatusPagamento] = mapped_column(
        Enum(StatusPagamento), default=StatusPagamento.PENDENTE, nullable=False
    )
    pago_em: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    observacoes: Mapped[str] = mapped_column(String(300), default="")

    # --- Cobrança automática (e-mails diários de D-1 do vencimento até o corte) ---
    ultimo_email_cobranca: Mapped[date] = mapped_column(Date, nullable=True)

    # --- Prorrogação emergencial de 12h (uso único por mensalidade em atraso) ---
    prorrogacao_utilizada: Mapped[bool] = mapped_column(Boolean, default=False)
    prorrogacao_expira: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # --- Pagamento via imprensa (comprovante anexado pela empresa) ---
    # A empresa anexa o comprovante e o pagamento fica "em processamento"
    # (aguardando_confirmacao=True) até a equipe financeira conferir e confirmar
    # manualmente; só então status vira PAGO e é de fato contabilizado.
    comprovante_path: Mapped[str] = mapped_column(String(400), nullable=True)
    aguardando_confirmacao: Mapped[bool] = mapped_column(Boolean, default=False)
    enviado_em: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class Aviso(SyncMixin, Base):
    """Avisos exibidos na tela de login, cadastrados pelo administrador."""
    __tablename__ = "avisos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String(150), nullable=False)
    mensagem: Mapped[str] = mapped_column(String(1000), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expira_em: Mapped[date] = mapped_column(Date, nullable=True)


class Configuracao(Base):
    """Configurações gerais do sistema (chave/valor)."""
    __tablename__ = "configuracoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chave: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    valor: Mapped[str] = mapped_column(String(300), nullable=False)


# UUID fixo (não gerado aleatoriamente) para que a linha de configuração da
# mensalidade seja SEMPRE a mesma em todas as instalações depois do sync —
# se cada instalação criasse a própria linha com um uuid aleatório, o sync
# trataria como registros diferentes em vez de mesclar num só.
UUID_CONFIGURACAO_PLATAFORMA = "00000000-0000-0000-0000-000000000001"


class ConfiguracaoPlataforma(SyncMixin, Base):
    """
    Configuração global da mensalidade cobrada pela plataforma (valor e
    dados do Pix usado para pagamento). Editada exclusivamente pelo super
    administrador no painel administrativo (admin_panel/app.py) e
    replicada para todas as instalações via sincronização normal (é uma
    tabela como qualquer outra, só que com uma única linha, de uuid fixo
    UUID_CONFIGURACAO_PLATAFORMA).
    """
    __tablename__ = "configuracoes_plataforma"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mensalidade_valor: Mapped[float] = mapped_column(Float, default=25.0)
    pix_chave: Mapped[str] = mapped_column(String(140), default="")
    pix_tipo_chave: Mapped[str] = mapped_column(String(20), default="E-mail")
    pix_nome_recebedor: Mapped[str] = mapped_column(String(25), default="")
    pix_cidade: Mapped[str] = mapped_column(String(15), default="")


class Produto(SyncMixin, Base):
    """Produto do estoque. Pode ser simples (comprado pronto) ou composto (produzido via ficha técnica).

    codigo_interno/codigo_barras/codigo_sku são únicos apenas dentro da
    mesma empresa (empresa_id) — cada comércio tem seu próprio catálogo,
    isolado dos demais mesmo compartilhando a mesma tabela/banco.
    """
    __tablename__ = "produtos"
    __table_args__ = (
        UniqueConstraint("empresa_id", "codigo_interno", name="uq_produto_codigo_interno_empresa"),
        UniqueConstraint("empresa_id", "codigo_barras", name="uq_produto_codigo_barras_empresa"),
        UniqueConstraint("empresa_id", "codigo_sku", name="uq_produto_codigo_sku_empresa"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=True)
    codigo_interno: Mapped[int] = mapped_column(Integer, nullable=False)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria: Mapped[str] = mapped_column(String(80), default="")
    codigo_barras: Mapped[str] = mapped_column(String(60), nullable=True)
    codigo_sku: Mapped[str] = mapped_column(String(60), nullable=True)
    unidade_medida: Mapped[str] = mapped_column(String(20), default="un")
    preco_custo: Mapped[float] = mapped_column(Float, default=0.0)
    preco_venda: Mapped[float] = mapped_column(Float, default=0.0)
    margem_lucro: Mapped[float] = mapped_column(Float, default=0.0)  # percentual

    # Estoques separados
    estoque_venda: Mapped[float] = mapped_column(Float, default=0.0)
    estoque_producao: Mapped[float] = mapped_column(Float, default=0.0)
    estoque_prateleira: Mapped[float] = mapped_column(Float, default=0.0)
    estoque_minimo: Mapped[float] = mapped_column(Float, default=0.0)

    composto: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    ingredientes: Mapped[list["ItemFichaTecnica"]] = relationship(
        back_populates="produto", foreign_keys="ItemFichaTecnica.produto_id", cascade="all, delete-orphan"
    )
    embalagens: Mapped[list["Embalagem"]] = relationship(back_populates="produto", cascade="all, delete-orphan")


class ItemFichaTecnica(SyncMixin, Base):
    """Ingrediente (com quantidade) de um produto composto (receita)."""
    __tablename__ = "itens_ficha_tecnica"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    ingrediente_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    quantidade: Mapped[float] = mapped_column(Float, nullable=False)
    unidade_medida: Mapped[str] = mapped_column(String(20), default="un")
    observacoes: Mapped[str] = mapped_column(String(300), default="")

    produto: Mapped["Produto"] = relationship(back_populates="ingredientes", foreign_keys=[produto_id])
    ingrediente: Mapped["Produto"] = relationship(foreign_keys=[ingrediente_id])


class Embalagem(SyncMixin, Base):
    """Embalagem/caixa de um produto (controle de caixas x unidades)."""
    __tablename__ = "embalagens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    codigo_caixa: Mapped[str] = mapped_column(String(60), nullable=True)
    qtd_unidades_por_caixa: Mapped[float] = mapped_column(Float, default=1.0)
    valor_caixa: Mapped[float] = mapped_column(Float, default=0.0)
    codigo_unidade: Mapped[str] = mapped_column(String(60), nullable=True)
    valor_unidade: Mapped[float] = mapped_column(Float, default=0.0)
    estoque_caixas: Mapped[float] = mapped_column(Float, default=0.0)
    estoque_unidades: Mapped[float] = mapped_column(Float, default=0.0)

    produto: Mapped["Produto"] = relationship(back_populates="embalagens")


class Venda(SyncMixin, Base):
    """Cabeçalho de uma venda (registra entrada automática no caixa)."""
    __tablename__ = "vendas"
    __table_args__ = (
        UniqueConstraint("empresa_id", "numero_venda", name="uq_venda_numero_empresa"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=True)
    numero_venda: Mapped[int] = mapped_column(Integer, nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    cliente: Mapped[str] = mapped_column(String(150), default="")
    data_hora: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    desconto_percentual: Mapped[float] = mapped_column(Float, default=0.0)
    acrescimo_percentual: Mapped[float] = mapped_column(Float, default=0.0)
    justificativa_acrescimo: Mapped[str] = mapped_column(String(300), default="")
    valor_total: Mapped[float] = mapped_column(Float, default=0.0)
    forma_pagamento: Mapped[str] = mapped_column(String(40), default="Dinheiro")
    cancelada: Mapped[bool] = mapped_column(Boolean, default=False)

    # Venda "em aberto" (carrinho deixado pendente para continuar depois, sem
    # travar a fila) ainda não desconta estoque nem tem pagamento definido.
    # `fechada_em` é preenchido quando a venda é finalizada e serve de base
    # para a limpeza automática do histórico (retenção de 3 meses).
    aberta: Mapped[bool] = mapped_column(Boolean, default=False)
    fechada_em: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    itens: Mapped[list["ItemVenda"]] = relationship(back_populates="venda", cascade="all, delete-orphan")
    pagamentos: Mapped[list["VendaPagamento"]] = relationship(back_populates="venda", cascade="all, delete-orphan")


class VendaPagamento(SyncMixin, Base):
    """Uma forma de pagamento usada em uma venda (permite pagamento dividido)."""
    __tablename__ = "vendas_pagamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venda_id: Mapped[int] = mapped_column(ForeignKey("vendas.id"), nullable=False)
    forma_pagamento: Mapped[str] = mapped_column(String(40), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)

    venda: Mapped["Venda"] = relationship(back_populates="pagamentos")


class ItemVenda(SyncMixin, Base):
    """Item (produto) de uma venda."""
    __tablename__ = "itens_venda"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venda_id: Mapped[int] = mapped_column(ForeignKey("vendas.id"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    quantidade: Mapped[float] = mapped_column(Float, nullable=False)
    valor_unitario: Mapped[float] = mapped_column(Float, nullable=False)
    valor_total: Mapped[float] = mapped_column(Float, nullable=False)
    estoque_insuficiente: Mapped[bool] = mapped_column(Boolean, default=False)

    venda: Mapped["Venda"] = relationship(back_populates="itens")
    produto: Mapped["Produto"] = relationship()


class CaixaSaida(SyncMixin, Base):
    """Saída manual de caixa (sempre vinculada a um usuário)."""
    __tablename__ = "caixa_saidas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    justificativa: Mapped[str] = mapped_column(String(300), nullable=False)
    categoria: Mapped[str] = mapped_column(String(80), default="")
    observacoes: Mapped[str] = mapped_column(String(500), default="")
    data_hora: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class MovimentoEstoque(SyncMixin, Base):
    """Transferência entre estoques (Venda <-> Produção <-> Prateleira) e reposições."""
    __tablename__ = "movimentos_estoque"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    origem: Mapped[str] = mapped_column(String(20), nullable=False)   # venda|producao|prateleira
    destino: Mapped[str] = mapped_column(String(20), nullable=False)  # venda|producao|prateleira
    quantidade: Mapped[float] = mapped_column(Float, nullable=False)
    motivo: Mapped[str] = mapped_column(String(300), default="")
    data_hora: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    produto: Mapped["Produto"] = relationship()


class Producao(SyncMixin, Base):
    """Registro de produção de um item composto (baixa automática dos ingredientes)."""
    __tablename__ = "producoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    quantidade_produzida: Mapped[float] = mapped_column(Float, nullable=False)
    custo_total: Mapped[float] = mapped_column(Float, default=0.0)
    data_hora: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    produto: Mapped["Produto"] = relationship()


class LogAlteracao(Base):

    """Histórico de alterações realizadas no sistema (auditoria)."""
    __tablename__ = "log_alteracoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario: Mapped[str] = mapped_column(String(120), default="desconhecido")
    acao: Mapped[str] = mapped_column(String(300), nullable=False)
    data_hora: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LogErro(Base):
    """Log de erros/exceções capturadas pela aplicação."""
    __tablename__ = "log_erros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mensagem: Mapped[str] = mapped_column(String(2000), nullable=False)
    origem: Mapped[str] = mapped_column(String(200), default="")
    data_hora: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Dispositivo(Base):
    """
    Registro de cada computador/instalação (device_id) que já sincronizou
    com a nuvem, conforme seção 6 da arquitetura de sincronização.
    Não participa do merge genérico (TABELAS_SINCRONIZAVEIS): é gravado
    diretamente, uma linha por device_id, local e na nuvem.
    """
    __tablename__ = "dispositivos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(120), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    ultima_sincronizacao: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class SyncQueue(Base):
    """
    Fila de eventos de sincronização (seção 7 da arquitetura): toda
    alteração feita neste device em uma tabela sincronizável gera uma
    linha aqui (INSERT/UPDATE/DELETE), preenchida automaticamente pelo
    listener `_registrar_evento_sync` abaixo. Serve de trilha de auditoria
    do que foi gerado localmente entre sincronizações; o merge de dados em
    si continua sendo feito pela comparação completa em sync_controller.py.
    """
    __tablename__ = "sync_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_name: Mapped[str] = mapped_column(String(60), nullable=False)
    record_id: Mapped[str] = mapped_column(String(36), nullable=False)  # uuid do registro
    operation: Mapped[str] = mapped_column(String(10), nullable=False)  # INSERT|UPDATE|DELETE
    device_id: Mapped[str] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[str] = mapped_column(String(15), default="PENDENTE")  # PENDENTE|SINCRONIZADO
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class SyncLog(Base):
    """Auditoria de cada ciclo de sincronização executado (seção 16)."""
    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(40), nullable=True)
    inicio: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fim: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    enviados: Mapped[int] = mapped_column(Integer, default=0)
    recebidos: Mapped[int] = mapped_column(Integer, default=0)
    erro: Mapped[str] = mapped_column(String(2000), nullable=True)


# --- Listener: preenche device_id/sync_version e alimenta a sync_queue --
# Disparado apenas na sessão LOCAL (SessionLocal, ver database.py) — o
# próprio sincronizador usa essa mesma sessão para aplicar dados vindos da
# nuvem, então alterações trazidas de fora também acabam gerando uma linha
# de fila aqui; isso é inofensivo (apenas reenvia um dado que já está
# igual nos dois lados) e mantém a lógica de detecção num único lugar.
def _registrar_evento_sync(session: Session, flush_context, instances) -> None:
    from database import engine_local
    try:
        if session.get_bind() is not engine_local:
            return
    except Exception:
        return
    device_id_atual = obter_device_id()
    for obj in list(session.new):
        if isinstance(obj, SyncMixin):
            if not obj.uuid:
                obj.uuid = str(uuid_lib.uuid4())
            if not obj.device_id:
                obj.device_id = device_id_atual
            session.add(SyncQueue(
                table_name=obj.__tablename__, record_id=obj.uuid,
                operation="INSERT", device_id=device_id_atual,
            ))
    for obj in list(session.dirty):
        if isinstance(obj, SyncMixin) and session.is_modified(obj, include_collections=False):
            obj.sync_version = (obj.sync_version or 0) + 1
            obj.device_id = device_id_atual
            operacao = "DELETE" if getattr(obj, "deletado", False) else "UPDATE"
            session.add(SyncQueue(
                table_name=obj.__tablename__, record_id=obj.uuid,
                operation=operacao, device_id=device_id_atual,
            ))


event.listen(Session, "before_flush", _registrar_evento_sync)

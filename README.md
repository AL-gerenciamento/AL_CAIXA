# 🔷 AL Caixa

Aplicativo desktop completo de controle financeiro pessoal, feito em Python com CustomTkinter, SQLAlchemy e SQLite.

## Tecnologias

- Python 3.13+
- CustomTkinter (interface gráfica)
- SQLAlchemy (ORM)
- SQLite (banco de dados)
- Matplotlib (gráficos)
- Pandas (exportação de dados)
- ReportLab (relatórios em PDF)
- bcrypt (senhas criptografadas)

## Instalação

```bash
# 1. Clone ou copie a pasta do projeto
cd controle_financeiro

# 2. (Recomendado) Crie um ambiente virtual
python3 -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows

# 3. Instale as dependências
pip install -r requirements.txt
```

No Linux, se faltar o Tkinter do sistema:
```bash
sudo apt-get install python3-tk
```

## Execução

```bash
python main.py
```

Na primeira execução:
1. O banco `database.db` e as tabelas são criados automaticamente.
2. As categorias padrão (Alimentação, Transporte, Salário etc.) são inseridas.
3. A tela de login aparece; como não há usuários, clique em **"Criar conta de administrador"** para cadastrar o primeiro usuário.

## Estrutura do projeto

```
controle_financeiro/
│
├── app.py               # Janela principal, splash screen, roteamento
├── main.py               # Ponto de entrada
├── database.py            # Engine/sessão SQLAlchemy
├── models.py              # Modelos (tabelas) do banco
├── controllers/            # Regras de negócio (um por entidade)
├── views/                # Telas CustomTkinter
├── assets/                # Ícones e imagens
├── reports/               # Log de erros e backups automáticos
├── utils/                # Validação, segurança, log
├── exports/               # Relatórios exportados (PDF/Excel/CSV)
├── database.db             # Banco SQLite (gerado automaticamente)
├── requirements.txt
└── README.md
```

## Funcionalidades

**Dashboard** — saldo atual, receitas, despesas, economia do mês, últimas movimentações, gráfico receitas x despesas, gráfico por categoria.

**Receitas / Despesas** — adicionar, editar, excluir, pesquisar por texto, filtrar por data e categoria. Despesas têm status "Paga" / "Pendente" (clique no botão de status para alternar).

**Categorias** — CRUD com cor personalizada, separadas em abas Receita/Despesa. Categorias com lançamentos vinculados não podem ser excluídas.

**Metas Financeiras** — criação de metas com valor alvo e prazo, barra de progresso visual, atualização manual do valor acumulado.

**Relatórios** — exportação em PDF, Excel (com aba detalhada + resumo agrupado) e CSV. Períodos pré-definidos e agrupamento por dia/semana/mês/ano/categoria.

**Configurações** — tema (claro/escuro/sistema), moeda, pasta de exportação, backup manual e restauração de backup. Administradores também gerenciam permissões e podem desativar usuários.

## Segurança

- Senhas armazenadas com hash bcrypt (nunca em texto puro).
- Todas as consultas usam SQLAlchemy ORM com parâmetros vinculados — sem concatenação de SQL, eliminando SQL Injection.
- Validação de todos os campos de formulário (`utils/validators.py`).
- Backup automático a cada 30 minutos (arquivo salvo em `reports/backups/`).
- Log de erros em `reports/erros.log` e na tabela `log_erros`.
- Histórico de alterações (auditoria) na tabela `log_alteracoes`.
- Dois níveis de permissão: **Administrador** e **Usuário**.

## Atalhos de teclado

| Atalho | Ação |
|---|---|
| Ctrl+D | Ir para Dashboard |
| Ctrl+R | Ir para Receitas |
| Ctrl+E | Ir para Despesas |
| Ctrl+M | Ir para Metas |
| Ctrl+Q | Fechar aplicativo |

## Backup e restauração

- **Criar backup**: Configurações → "Criar Backup Agora" (copia `database.db` para `reports/backups/`).
- **Restaurar backup**: Configurações → "Restaurar Backup..." → selecione um arquivo `.db`. Reinicie o aplicativo após restaurar.

## Solução de problemas

- **Erro de módulo Tkinter ausente**: instale `python3-tk` (Linux) — Windows/Mac já incluem por padrão.
- **Erro ao gerar PDF/Excel**: confirme que `reportlab`, `pandas` e `openpyxl` foram instalados corretamente (`pip install -r requirements.txt`).
- **Esqueci a senha de admin**: não há recuperação automática por segurança; peça a outro administrador para alterar permissões, ou restaure um backup anterior do `database.db`.

## Instaladores (Windows / macOS / Linux)

Veja `packaging/` para os scripts de build (PyInstaller + Inno Setup/DMG/AppImage)
e `.github/workflows/build.yml` para gerar os três instaladores automaticamente
via GitHub Actions a cada tag `vX.Y.Z`.

### Credenciais (SMTP, DATABASE_URL, etc.)

O `.env` real (com senhas) **nunca** é empacotado no executável — os `.spec`
em `packaging/` embutem só um `.env` em branco, gerado a partir de
`.env.example`. Depois de instalar em uma máquina nova:

1. Rode o app uma vez (cria a pasta persistente, ex.: `Documents/AL Caixa`).
2. Feche o app e edite `Documents/AL Caixa/.env` com as credenciais reais
   (`DATABASE_URL`, `SMTP_*`, `SUPABASE_SYNC_FUNCTION_URL`).
3. Abra o app de novo.

Atualizações automáticas nunca sobrescrevem esse `.env` (ver `utils/atualizador.py`).
O arquivo `.env` da raiz do projeto (usado só em modo dev, sem empacotar) não
deve ser commitado — está no `.gitignore`; use `.env.example` como modelo.

## Atualização automática

O app verifica sozinho por novas versões publicadas no Google Drive.
Especificação técnica completa e passo a passo de publicação: `ATUALIZACOES.txt`.

## Controle de acesso à nuvem por empresa

Painel Super Admin -> aba Empresas -> botão "Bloquear nuvem/Liberar nuvem"
(independente do bloqueio de login por mensalidade). Detalhes em `ATUALIZACOES.txt`.

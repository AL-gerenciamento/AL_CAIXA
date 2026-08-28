# AL Caixa — Gestão Inteligente

Sistema de caixa (PDV) e gestão financeira para mercados e pequenos negócios, com
aplicativo desktop (Windows/macOS/Linux), funcionamento **offline-first** e
sincronização automática em nuvem.

## Visão geral

- **PDV completo**: leitura por código de barras/código interno/nome, carrinho,
  finalização com baixa automática de estoque e caixa, recibo em PDF/WhatsApp.
- **Estoque em 3 camadas**: Venda, Produção Interna e Prateleira, com transferências
  entre elas e bloqueio automático de produção quando falta ingrediente.
- **Produtos compostos**: ficha técnica com ingredientes, cálculo automático de
  custo e formação de preço por margem.
- **Financeiro**: receitas, despesas (avulsas e fixas recorrentes), categorias,
  metas financeiras com progresso visual.
- **Relatórios**: resumo com gráficos e exportação em PDF, Excel e CSV.
- **Multiusuário**: permissões granulares por módulo, hierarquia de usuários,
  painel de administração.
- **Offline-first**: banco local SQLite com fila de sincronização; funciona sem
  internet e sincroniza automaticamente ao reconectar.
- **Atualização automática**: verifica e aplica novas versões via Google Drive,
  sem reinstalação manual (ver `ATUALIZACOES.txt`).
- **Central de Ajuda** integrada, com manual pesquisável por módulo.

## Arquitetura

```
app.py                  # janela raiz: splash, login, roteamento entre telas
main.py                 # ponto de entrada
database.py             # engine SQLAlchemy, sessão, modo REST/nuvem
models.py               # modelos de dados (Empresa, Usuario, Produto, Venda, ...)
controllers/             # regras de negócio (uma por domínio)
views/                   # telas CustomTkinter (uma por módulo)
utils/                   # autenticação, criptografia local, PIX, impressão, etc.
supabase/                # SQL de RLS/triggers e Edge Functions (Deno/TS)
admin_panel/             # painel Super Admin (app separado)
packaging/               # specs PyInstaller e scripts de build por SO
```

**Padrão**: `views/` (UI) → `controllers/` (regras de negócio) → `models.py`
(SQLAlchemy) → `database.py` (SQLite local, com sync para Supabase/Postgres em
nuvem via `controllers/sync_controller.py`).

### Fluxo de sessão

`App` (`app.py`) controla: `_mostrar_login()` → `_entrar_no_sistema()` →
`_construir_area_principal()`. O botão **Sair** encerra apenas a sessão do
usuário e volta à tela de login (`_sair_da_conta`); fechar a janela ou `Ctrl+Q`
encerra o aplicativo (`_fechar`).

## Tecnologias

| Camada | Tecnologia |
|---|---|
| UI desktop | CustomTkinter |
| ORM / banco local | SQLAlchemy + SQLite |
| Nuvem | Supabase (Postgres + Edge Functions) |
| Gráficos | Matplotlib |
| Relatórios | ReportLab (PDF), openpyxl/pandas (Excel/CSV) |
| Imagens/etiquetas | Pillow, PyMuPDF |
| Impressão | pywin32 (GDI direto no Windows) |
| Segurança | bcrypt, cryptography |
| Empacotamento | PyInstaller (`packaging/*.spec`), Inno Setup (Windows) |

## Executando em desenvolvimento

```bash
pip install -r requirements.txt
cp .env.example .env   # preencha as credenciais do Supabase, se for usar nuvem
python main.py
```

## Build de instaladores

```bash
packaging/build_windows.bat   # Windows (.exe único via PyInstaller + Inno Setup)
packaging/build_macos.sh      # macOS (.app)
packaging/build_linux.sh      # Linux
```

Detalhes do processo de publicação de nova versão e do sistema de atualização
automática: ver `ATUALIZACOES.txt`.

## Estrutura de permissões

Usuários têm um `Permissao` (`ADMIN`/padrão) e permissões granulares por
módulo (`Usuario.tem_permissao`). Módulos sem permissão não aparecem na grade
do Dashboard e têm o acesso bloqueado na navegação (`app.py::_navegar`).

## Suporte

E-mail: `algl.gerenciamento@gmail.com` — Segunda a sexta-feira, 14h–18h
(horário de Brasília). Manual completo dentro do app em **Central de Ajuda**.

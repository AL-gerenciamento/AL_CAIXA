"""
views/ajuda_view.py
Central de Ajuda e Suporte (item 17): manual do sistema com explicação,
objetivo, passo a passo, exemplos, dicas e FAQ de cada funcionalidade,
busca por assunto e tela de contato com o suporte (sem envio automático
por e-mail: abre o aplicativo de e-mail padrão do usuário).
"""
import platform
import webbrowser

import customtkinter as ctk
from tkinter import messagebox

EMAIL_SUPORTE = "algl.gerenciamento@gmail.com"
HORARIO_SUPORTE = "Segunda a sexta-feira, das 14h00 às 18h00 (horário de Brasília)."

MANUAL = [
    {
        "titulo": "Cadastro de Produtos",
        "explicacao": "Cadastre cada produto do seu negócio com um código interno sequencial "
                       "gerado automaticamente, além de código de barras e/ou SKU opcionais.",
        "objetivo": "Manter um catálogo único e organizado de tudo o que é vendido ou usado na produção.",
        "passo_a_passo": "Vá em Produtos → + Novo Produto → preencha nome, categoria, preços e estoque inicial → Salvar.",
        "exemplo": "Produto 1 = Leite Condensado, Produto 2 = Creme de Leite, Produto 3 = Chocolate em Pó.",
        "dicas": "Preencha o estoque mínimo para receber alertas de estoque baixo no Dashboard.",
        "faq": "P: Posso mudar o código interno depois? R: Não, ele é único e permanente.",
    },
    {
        "titulo": "Controle de Estoque",
        "explicacao": "Toda venda desconta o estoque automaticamente.",
        "objetivo": "Manter a quantidade disponível sempre atualizada sem lançamentos manuais.",
        "passo_a_passo": "Nada a fazer manualmente: a baixa ocorre ao finalizar uma venda no PDV.",
        "exemplo": "Se restam 3 unidades e você vende 5, o sistema pergunta se deseja continuar mesmo assim.",
        "dicas": "Use o campo 'estoque mínimo' do produto para saber quando repor.",
        "faq": "P: O estoque pode ficar negativo? R: Sim, se a venda for confirmada mesmo com falta de estoque.",
    },
    {
        "titulo": "Estoque de Produção vs. Estoque de Venda",
        "explicacao": "Existem estoques separados: Venda, Produção Interna e Prateleira.",
        "objetivo": "Evitar que a matéria-prima usada na produção seja vendida por engano.",
        "passo_a_passo": "Em Estoque → Transferências, mova quantidades entre Venda, Produção e Prateleira.",
        "exemplo": "Transferir 10 caixas de leite condensado do estoque de Venda para Produção antes de produzir brigadeiros.",
        "dicas": "Produtos compostos só descontam do estoque de Produção Interna.",
        "faq": "P: Posso reverter uma transferência? R: Sim, faça uma nova transferência no sentido oposto.",
    },
    {
        "titulo": "Controle de Prateleira",
        "explicacao": "A prateleira é um estoque específico para o que está exposto para venda imediata.",
        "objetivo": "Saber sempre quanto está disponível na loja/balcão.",
        "passo_a_passo": "Em Estoque → Prateleira, use 'Repor' para levar do estoque geral à prateleira, ou 'Retornar' para o caminho inverso.",
        "exemplo": "Repor 20 unidades de um produto na prateleira antes da abertura da loja.",
        "dicas": "A venda desconta primeiro da prateleira e só depois do estoque geral.",
        "faq": "P: A prateleira soma no estoque total do Dashboard? R: Sim.",
    },
    {
        "titulo": "Caixa (Entradas e Saídas)",
        "explicacao": "Toda venda gera uma entrada automática no caixa. Saídas são registradas manualmente e sempre vinculadas a um usuário.",
        "objetivo": "Ter um controle auditável de tudo que entra e sai do caixa.",
        "passo_a_passo": "Para uma saída: PDV → Saída de Caixa → informe valor e justificativa (obrigatórios) → Registrar.",
        "exemplo": "Saída de R$ 50,00 com justificativa 'Compra de embalagens'.",
        "dicas": "Categoria e observações são opcionais, mas ajudam nos relatórios.",
        "faq": "P: Posso excluir uma saída de caixa? R: Não; todo lançamento fica registrado para auditoria.",
    },
    {
        "titulo": "Vendas e Leitura por Código de Barras",
        "explicacao": "No PDV, digite ou leia o código de barras, código interno ou nome do produto para adicioná-lo à venda.",
        "objetivo": "Agilizar o registro da venda.",
        "passo_a_passo": "PDV → digite/leia o código no campo de busca → Enter → ajuste quantidade → Finalizar Venda.",
        "exemplo": "Ler o código de barras impresso na embalagem do produto com um leitor USB.",
        "dicas": "Se não houver leitor, basta digitar o nome do produto.",
        "faq": "P: Funciona com qualquer leitor USB? R: Sim, leitores USB funcionam como um teclado.",
    },
    {
        "titulo": "Produtos Compostos e Ficha Técnica",
        "explicacao": "Produtos produzidos internamente (ex.: Brigadeiro) têm uma ficha técnica com os ingredientes e quantidades usadas.",
        "objetivo": "Calcular automaticamente o custo de produção e descontar os ingredientes corretos.",
        "passo_a_passo": "Produtos → editar o produto composto → aba Ficha Técnica → adicione ingredientes e quantidades → Salvar.",
        "exemplo": "Brigadeiro = 1 caixa de leite condensado + 25g de chocolate + 100mL de creme de leite.",
        "dicas": "Cadastre os ingredientes como produtos comuns antes de montar a ficha técnica.",
        "faq": "P: O custo do composto é automático? R: Sim, recalculado a cada alteração da ficha técnica.",
    },
    {
        "titulo": "Formação de Preço",
        "explicacao": "O preço de venda pode ser definido diretamente ou calculado a partir de uma margem de lucro desejada.",
        "objetivo": "Facilitar a precificação com base no custo real do produto.",
        "passo_a_passo": "No formulário do produto, informe o preço de venda OU a margem % desejada.",
        "exemplo": "Custo R$ 6,65 + margem de 100% = preço de venda R$ 13,30.",
        "dicas": "Acompanhe a margem de lucro exibida após salvar a ficha técnica.",
        "faq": "P: Alterar o custo recalcula o preço automaticamente? R: A margem é recalculada; o preço só muda se você usar 'definir preço por margem'.",
    },
    {
        "titulo": "Produção",
        "explicacao": "Ao produzir um item composto, os ingredientes são descontados do estoque de Produção e o produto final entra no estoque de Venda.",
        "objetivo": "Registrar oficialmente cada lote produzido, com custo e data.",
        "passo_a_passo": "Estoque → aba Produção → selecione o produto composto → informe a quantidade → Produzir.",
        "exemplo": "Produzir 20 brigadeiros consome os ingredientes na proporção da ficha técnica.",
        "dicas": "O sistema mostra quanto ainda pode ser produzido com o estoque atual antes de você confirmar.",
        "faq": "P: E se faltar ingrediente? R: O sistema bloqueia a produção e informa qual ingrediente está em falta.",
    },
    {
        "titulo": "Recibo de Venda",
        "explicacao": "Ao concluir uma venda, um recibo é gerado automaticamente com todos os dados da venda.",
        "objetivo": "Entregar comprovante ao cliente.",
        "passo_a_passo": "Ao finalizar a venda, a janela de recibo abre com opções de exportar PDF ou enviar por WhatsApp.",
        "exemplo": "Enviar o recibo em PDF pelo WhatsApp digitando o telefone do cliente.",
        "dicas": "O PDF fica salvo na pasta de exportação configurada em Configurações.",
        "faq": "P: Dá para enviar por e-mail? R: Não; esse recibo é disponibilizado apenas em PDF e WhatsApp.",
    },
    {
        "titulo": "Dashboard",
        "explicacao": "Mostra em tempo real produtos em estoque/prateleira, estoque baixo/negativo, valor do estoque, vendas e saldo do caixa do dia.",
        "objetivo": "Dar uma visão geral rápida da operação.",
        "passo_a_passo": "Acesse Dashboard no menu lateral.",
        "exemplo": "Ver de relance quais produtos estão com estoque baixo hoje.",
        "dicas": "Use os indicadores de estoque baixo para planejar reposições.",
        "faq": "P: Os dados são atualizados automaticamente? R: Sim, a cada visita à tela.",
    },
]


class AjudaView(ctk.CTkFrame):
    """Central de Ajuda: manual pesquisável + tela de contato com suporte."""

    def __init__(self, master, usuario):
        super().__init__(master, fg_color="transparent")
        self.usuario = usuario
        self._construir_layout()

    def _construir_layout(self) -> None:
        ctk.CTkLabel(self, text="Central de Ajuda", font=ctk.CTkFont(size=26, weight="bold")).pack(
            anchor="w", padx=30, pady=(25, 10)
        )
        abas = ctk.CTkTabview(self)
        abas.pack(fill="both", expand=True, padx=30, pady=(0, 25))

        aba_manual = abas.add("Manual do Sistema")
        aba_suporte = abas.add("Falar com o Suporte")
        self._construir_manual(aba_manual)
        self._construir_suporte(aba_suporte)

    # --- Manual pesquisável ---
    def _construir_manual(self, aba) -> None:
        self.entry_busca = ctk.CTkEntry(aba, placeholder_text="Pesquisar assunto na Central de Ajuda...", width=500)
        self.entry_busca.pack(pady=(15, 10))
        self.entry_busca.bind("<KeyRelease>", lambda e: self._atualizar_manual())

        self.lista_manual = ctk.CTkScrollableFrame(aba)
        self.lista_manual.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._atualizar_manual()

    def _atualizar_manual(self) -> None:
        for w in self.lista_manual.winfo_children():
            w.destroy()

        termo = self.entry_busca.get().strip().lower()
        itens = MANUAL if not termo else [
            item for item in MANUAL
            if termo in " ".join(str(v) for v in item.values()).lower()
        ]

        if not itens:
            ctk.CTkLabel(self.lista_manual, text="Nenhum assunto encontrado.").pack(pady=20)
            return

        for item in itens:
            bloco = ctk.CTkFrame(self.lista_manual, corner_radius=8)
            bloco.pack(fill="x", pady=6, padx=4)
            ctk.CTkLabel(bloco, text=item["titulo"], font=ctk.CTkFont(size=15, weight="bold")).pack(
                anchor="w", padx=12, pady=(10, 4)
            )
            campos = [
                ("Explicação", item["explicacao"]),
                ("Objetivo", item["objetivo"]),
                ("Passo a passo", item["passo_a_passo"]),
                ("Exemplo prático", item["exemplo"]),
                ("Dicas", item["dicas"]),
                ("FAQ", item["faq"]),
            ]
            for rotulo, texto in campos:
                ctk.CTkLabel(
                    bloco, text=f"{rotulo}: {texto}", anchor="w", justify="left", wraplength=880
                ).pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(bloco, text="").pack(pady=2)

    # --- Suporte ---
    def _construir_suporte(self, aba) -> None:
        ctk.CTkLabel(aba, text=f"E-mail de suporte: {EMAIL_SUPORTE}", anchor="w").pack(fill="x", padx=10, pady=(15, 4))
        ctk.CTkLabel(aba, text=f"Horário de atendimento: {HORARIO_SUPORTE}", anchor="w").pack(fill="x", padx=10, pady=4)

        ctk.CTkLabel(aba, text="Descreva o problema:", anchor="w").pack(fill="x", padx=10, pady=(15, 4))
        self.texto_problema = ctk.CTkTextbox(aba, height=140)
        self.texto_problema.pack(fill="x", padx=10, pady=4)

        self.var_diagnostico = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            aba, text="Incluir informações técnicas (versão do sistema e sistema operacional)",
            variable=self.var_diagnostico
        ).pack(anchor="w", padx=10, pady=8)

        ctk.CTkButton(
            aba, text="Abrir e-mail para o suporte", width=280, command=self._abrir_email_suporte
        ).pack(padx=10, pady=15, anchor="w")

    def _abrir_email_suporte(self) -> None:
        """Abre o aplicativo de e-mail padrão do usuário com o endereço de suporte preenchido
        (não realiza o envio automaticamente)."""
        corpo = self.texto_problema.get("1.0", "end").strip()
        if self.var_diagnostico.get():
            corpo += (
                f"\n\n--- Informações técnicas ---\nSistema operacional: {platform.system()} {platform.release()}"
            )
        assunto = "Suporte - Sistema de Gestão"
        try:
            import urllib.parse
            url = f"mailto:{EMAIL_SUPORTE}?subject={urllib.parse.quote(assunto)}&body={urllib.parse.quote(corpo)}"
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o aplicativo de e-mail: {e}")

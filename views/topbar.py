import customtkinter as ctk

COR_FUNDO = ("gray92", "gray14")
COR_HOVER = ("gray80", "gray25")
COR_ATIVO = "#3B8ED0"
COR_TEXTO = ("gray15", "gray90")
COR_TEXTO_SUAVE = ("gray35", "gray70")


class TopBar(ctk.CTkFrame):
    def __init__(self, master, ao_selecionar, usuario):
        super().__init__(master, height=52, corner_radius=0, fg_color=COR_FUNDO)
        self.ao_selecionar = ao_selecionar
        self.usuario = usuario

        self.grid_propagate(False)
        self._construir()

    def _construir(self) -> None:
        ctk.CTkLabel(
            self, text="AL Caixa", font=ctk.CTkFont(size=19, weight="bold", slant="italic"),
            text_color=COR_TEXTO,
        ).pack(side="left", padx=(18, 24))

        ctk.CTkButton(
            self, text="🏠  Dashboard", anchor="center", height=36,
            fg_color=COR_ATIVO, hover_color=COR_HOVER, text_color="white",
            command=lambda: self.ao_selecionar("Dashboard"),
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            self, text="Sair", width=70, height=32, fg_color="transparent",
            hover_color=COR_HOVER, text_color=COR_TEXTO_SUAVE,
            command=lambda: self.ao_selecionar("__sair__"),
        ).pack(side="right", padx=(4, 18))

        ctk.CTkLabel(
            self, text=f"Olá, {self.usuario.nome.split()[0]}", text_color=COR_TEXTO_SUAVE,
        ).pack(side="right", padx=4)

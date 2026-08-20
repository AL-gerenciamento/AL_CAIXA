"""
utils/validators.py
Validações reutilizáveis de campos de formulário.
Como toda a aplicação usa SQLAlchemy ORM com parâmetros vinculados
(bind parameters), consultas SQL cruas nunca são concatenadas manualmente,
o que já elimina o vetor clássico de SQL Injection.
"""
from datetime import datetime


class ValidationError(Exception):
    """Exceção lançada quando um campo de formulário é inválido."""
    pass

UNIDADES_FRACIONAVEIS = {"kg", "l"}


def unidade_permite_fracao(unidade: str) -> bool:
    """Só kg e L aceitam quantidade decimal; as demais unidades são inteiras."""
    return (unidade or "").strip().lower() in UNIDADES_FRACIONAVEIS


def ajustar_quantidade_para_unidade(quantidade: float, unidade: str) -> float:
    """Arredonda para inteiro quando a unidade não permite fração (só kg/L fracionam)."""
    if unidade_permite_fracao(unidade):
        return quantidade
    return float(round(quantidade))



def validar_texto_obrigatorio(valor: str, campo: str, tamanho_max: int = 200) -> str:
    """Garante que um texto não esteja vazio e respeite tamanho máximo."""
    valor = (valor or "").strip()
    if not valor:
        raise ValidationError(f"O campo '{campo}' é obrigatório.")
    if len(valor) > tamanho_max:
        raise ValidationError(f"O campo '{campo}' excede {tamanho_max} caracteres.")
    return valor


def validar_valor_monetario(valor: str) -> float:
    """Converte e valida um valor monetário (aceita vírgula ou ponto)."""
    try:
        valor_normalizado = str(valor).strip().replace(".", "").replace(",", ".") \
            if "," in str(valor) else str(valor).strip()
        numero = float(valor_normalizado)
    except (ValueError, TypeError):
        raise ValidationError("Valor monetário inválido.")
    if numero <= 0:
        raise ValidationError("O valor deve ser maior que zero.")
    return round(numero, 2)


def validar_data(valor: str, formato: str = "%d/%m/%Y") -> datetime:
    """Converte e valida uma data no formato brasileiro dd/mm/aaaa."""
    try:
        return datetime.strptime(valor.strip(), formato)
    except (ValueError, AttributeError):
        raise ValidationError("Data inválida. Use o formato dd/mm/aaaa.")


def validar_login(login: str) -> str:
    """Valida um nome de login (sem espaços, mínimo 3 caracteres)."""
    login = (login or "").strip()
    if len(login) < 3:
        raise ValidationError("O login deve ter ao menos 3 caracteres.")
    if " " in login:
        raise ValidationError("O login não pode conter espaços.")
    return login


def validar_senha(senha: str) -> str:
    """Valida força mínima de senha."""
    if not senha or len(senha) < 4:
        raise ValidationError("A senha deve ter ao menos 4 caracteres.")
    return senha


def _apenas_digitos(valor: str) -> str:
    return "".join(ch for ch in (valor or "") if ch.isdigit())


def validar_cpf(cpf: str) -> str:
    cpf = _apenas_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        raise ValidationError("CPF inválido.")
    for i in (9, 10):
        soma = sum(int(cpf[num]) * ((i + 1) - num) for num in range(0, i))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[i]):
            raise ValidationError("CPF inválido.")
    return cpf


def validar_cnpj(cnpj: str) -> str:
    cnpj = _apenas_digitos(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        raise ValidationError("CNPJ inválido.")
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(cnpj[i]) * pesos1[i] for i in range(12))
    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto
    if digito1 != int(cnpj[12]):
        raise ValidationError("CNPJ inválido.")
    soma = sum(int(cnpj[i]) * pesos2[i] for i in range(13))
    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto
    if digito2 != int(cnpj[13]):
        raise ValidationError("CNPJ inválido.")
    return cnpj


def validar_nome_empresa(nome: str) -> str:
    return validar_texto_obrigatorio(nome, "Nome da empresa", 150)


def validar_sigla(sigla: str) -> str:
    sigla = (sigla or "").strip().upper()
    if not (2 <= len(sigla) <= 20):
        raise ValidationError("A sigla da empresa deve ter entre 2 e 20 caracteres.")
    if not sigla.isalnum():
        raise ValidationError("A sigla da empresa deve conter apenas letras e números.")
    return sigla


def validar_nome_usuario_login(login: str) -> str:
    login = (login or "").strip()
    if len(login) < 3:
        raise ValidationError("O nome de usuário deve ter ao menos 3 caracteres.")
    if " " in login or "@" in login:
        raise ValidationError("O nome de usuário não pode conter espaços ou '@'.")
    return login

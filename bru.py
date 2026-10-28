import argparse
import re
import sys
from dataclasses import dataclass, field


# ---------- erros ----------
class ErroBru(Exception):
    def __init__(self, etapa, linha, msg):
        super().__init__(msg)
        self.etapa, self.linha, self.msg = etapa, linha, msg


# ---------- 1. TOKENIZADOR: texto -> tokens ----------
@dataclass
class Token:
    tipo: str    
    valor: str
    linha: int


PADRAO_TOKEN = re.compile(r"""
    (?P<NUMBER>-?\d+(?:\.\d+)?(?![\w.]))
  | (?P<WORD>\w+)
  | (?P<DASH>-)
  | (?P<COLON>:)
  | (?P<SEMI>;)
  | (?P<SKIP>[ \t\r]+)
  | (?P<ERRO>.)
""", re.VERBOSE)


def tokenizar(texto):
    tokens = []
    for n, linha in enumerate(texto.split("\n"), start=1):
        linha = linha.split("#", 1)[0]           
        if not linha.strip():                    
            continue
        for m in PADRAO_TOKEN.finditer(linha):
            tipo, valor = m.lastgroup, m.group()
            if tipo == "SKIP":
                continue
            if tipo == "ERRO":
                raise ErroBru("léxico", n, f"caractere inesperado {valor!r}")
            if tipo == "WORD" and valor == "alert":
                tipo = "ALERT"
            tokens.append(Token(tipo, valor, n))
        tokens.append(Token("NEWLINE", "\n", n))
    tokens.append(Token("EOF", "", len(texto.split("\n"))))
    return tokens


# ---------- 2. PARSER: tokens -> AST ----------
@dataclass
class Propriedade:
    chave: str
    valor: float
    linha: int


@dataclass
class Alerta:
    nome: str
    linha: int
    propriedades: list = field(default_factory=list)


def parsear(tokens):
    pos = 0

    def atual():
        return tokens[pos]

    def esperar(tipo, o_que):
        nonlocal pos
        t = atual()
        if t.tipo != tipo:
            achado = "fim da linha" if t.tipo == "NEWLINE" else \
                     "fim do arquivo" if t.tipo == "EOF" else repr(t.valor)
            raise ErroBru("sintático", t.linha, f"esperado {o_que}, mas encontrei {achado}")
        pos += 1
        return t

    alertas = []
    while atual().tipo != "EOF":
        if atual().tipo == "DASH":
            raise ErroBru("sintático", atual().linha, "propriedade fora de um alerta")
        inicio = esperar("ALERT", "'alert'")
        if atual().tipo == "SEMI":
            raise ErroBru("sintático", inicio.linha, "alerta sem nome")
        nome = esperar("WORD", "o nome do alerta")
        esperar("SEMI", "';' depois do nome (nomes não podem ter espaços nem símbolos)")
        esperar("NEWLINE", "fim da linha depois de ';'")
        alerta = Alerta(nome.valor, inicio.linha)
        while atual().tipo == "DASH":            # uma propriedade por linha
            esperar("DASH", "'-'")
            chave = esperar("WORD", "o nome da propriedade")
            esperar("COLON", "':'")
            valor = esperar("NUMBER", "um número")
            esperar("NEWLINE", "fim da linha (uma propriedade por linha)")
            numero = float(valor.valor) if "." in valor.valor else int(valor.valor)
            alerta.propriedades.append(Propriedade(chave.valor, numero, chave.linha))
        alertas.append(alerta)
    return alertas


# ---------- 3. SEMÂNTICA: regras de validação ----------
def validar(alertas):
    erros = []
    nomes_vistos = {}
    for a in alertas:
        if not re.fullmatch(r"[^\W\d_]\w*", a.nome):
            erros.append((a.linha, f"nome inválido '{a.nome}' (deve começar por letra)"))
        if a.nome in nomes_vistos:
            erros.append((a.linha, f"nome repetido '{a.nome}' (já usado na linha {nomes_vistos[a.nome]})"))
        nomes_vistos.setdefault(a.nome, a.linha)

        chaves = {}
        for p in a.propriedades:
            if p.chave not in ("min", "max"):
                erros.append((p.linha, f"chave desconhecida '{p.chave}' (só 'min' e 'max')"))
            elif p.chave in chaves:
                erros.append((p.linha, f"chave '{p.chave}' repetida no alerta '{a.nome}'"))
            else:
                chaves[p.chave] = p.valor
        if not chaves:
            erros.append((a.linha, f"alerta '{a.nome}' sem 'min' e sem 'max'"))
        elif "min" in chaves and "max" in chaves and chaves["min"] > chaves["max"]:
            erros.append((a.linha, f"limites invertidos em '{a.nome}': min ({chaves['min']}) > max ({chaves['max']})"))
    return erros


# ---------- 4. GERADOR: AST -> Python ----------
CABECALHO = '''\
# Arquivo GERADO por bru.py a partir de {origem}. Não edite à mão.
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Alerta:
    nome: str
    minimo: Optional[float] = None
    maximo: Optional[float] = None

    def disparou(self, valor):
        """True se o valor ficou fora do intervalo [minimo, maximo]."""
        if self.minimo is not None and valor < self.minimo:
            return True
        if self.maximo is not None and valor > self.maximo:
            return True
        return False


ALERTAS = [
'''


def gerar(alertas, origem):
    linhas = [CABECALHO.format(origem=origem)]
    for a in alertas:
        props = {p.chave: p.valor for p in a.propriedades}
        args = [f"nome={a.nome!r}"]
        if "min" in props:
            args.append(f"minimo={props['min']!r}")
        if "max" in props:
            args.append(f"maximo={props['max']!r}")
        linhas.append(f"    Alerta({', '.join(args)}),\n")
    linhas.append("]\n")
    return "".join(linhas)


# ---------- programa principal ----------
def transpilar(texto, origem="entrada.bru"):
    tokens = tokenizar(texto)
    ast = parsear(tokens)
    erros = validar(ast)
    if erros:
        raise ErroBru("semântico", erros[0][0],
                      "\n".join(f"{origem}:{l}: erro semântico: {m}" for l, m in sorted(erros)))
    return gerar(ast, origem)


def main():
    ap = argparse.ArgumentParser(description="Transpilador .bru -> Python")
    ap.add_argument("entrada")
    ap.add_argument("-o", "--saida", help="arquivo .py de saída (padrão: mesmo nome, extensão .py)")
    args = ap.parse_args()
    saida = args.saida or re.sub(r"\.bru$", "", args.entrada) + ".py"
    try:
        with open(args.entrada, encoding="utf-8") as f:
            codigo = transpilar(f.read(), args.entrada)
    except ErroBru as e:
        if e.etapa == "semântico":
            print(e.msg, file=sys.stderr)
        else:
            print(f"{args.entrada}:{e.linha}: erro {e.etapa}: {e.msg}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"arquivo não encontrado: {args.entrada}", file=sys.stderr)
        sys.exit(1)
    with open(saida, "w", encoding="utf-8") as f:
        f.write(codigo)
    print(f"OK: {saida} gerado")


if __name__ == "__main__":
    main()

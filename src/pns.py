import re
from pathlib import Path

import pandas as pd


def extrair_layout_pns(caminho_input):
    """
    Lê o arquivo de input SAS da PNS, salvo em formato TXT,
    e extrai o layout necessário para ler os microdados
    de largura fixa.

    Parâmetros
    ----------
    caminho_input : str ou pathlib.Path
        Caminho do arquivo input_PNS_2019.txt.

    Retorno
    -------
    pandas.DataFrame
        DataFrame contendo:
        - variavel
        - inicio_sas
        - fim_sas
        - inicio_python
        - fim_python
        - largura
        - decimais
        - tipo_sas
    """

    caminho_input = Path(caminho_input)

    if not caminho_input.exists():
        raise FileNotFoundError(
            f"Arquivo de input não encontrado: {caminho_input}"
        )

    texto = None

    for encoding in ["utf-8", "cp1252", "latin-1"]:
        try:
            texto = caminho_input.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue

    if texto is None:
        raise ValueError(
            "Não foi possível identificar a codificação do arquivo de input."
        )

    padrao = re.compile(
        r"""
        @\s*(?P<inicio>\d+)
        \s+
        (?P<variavel>[A-Za-z_][A-Za-z0-9_]*)
        \s+
        (?P<texto>\$)?
        (?P<largura>\d+)
        (?:\.(?P<decimais>\d*))?
        """,
        flags=re.VERBOSE,
    )

    registros = []

    for numero_linha, linha in enumerate(texto.splitlines(), start=1):
        linha = linha.strip()

        if not linha.startswith("@"):
            continue

        resultado = padrao.match(linha)

        if resultado is None:
            raise ValueError(
                f"Não foi possível interpretar a linha {numero_linha}:\n"
                f"{linha}"
            )

        inicio_sas = int(resultado.group("inicio"))
        largura = int(resultado.group("largura"))

        decimais_texto = resultado.group("decimais")

        if decimais_texto in (None, ""):
            decimais = 0
        else:
            decimais = int(decimais_texto)

        eh_texto = resultado.group("texto") == "$"

        registros.append(
            {
                "variavel": resultado.group("variavel"),
                "inicio_sas": inicio_sas,
                "fim_sas": inicio_sas + largura - 1,
                "inicio_python": inicio_sas - 1,
                "fim_python": inicio_sas - 1 + largura,
                "largura": largura,
                "decimais": decimais,
                "tipo_sas": "caractere" if eh_texto else "numerico",
            }
        )

    if not registros:
        raise ValueError(
            "Nenhuma especificação de variável foi encontrada no input."
        )

    layout = pd.DataFrame(registros)

    layout = (
        layout
        .drop_duplicates(subset="variavel", keep="first")
        .sort_values("inicio_sas")
        .reset_index(drop=True)
    )

    return layout

def ler_pns(
    caminho_microdados,
    caminho_input,
    variaveis=None,
    converter_numericas=True,
    filtrar_entrevistas=True,
):
    """
    Lê os microdados da PNS em formato de largura fixa.

    Parâmetros
    ----------
    caminho_microdados : str ou pathlib.Path
        Caminho do arquivo bruto PNS_2019.txt.

    caminho_input : str ou pathlib.Path
        Caminho do arquivo input_PNS_2019.txt.

    variaveis : list[str], str ou None
        Variáveis que devem ser importadas.
        Se None, todas as variáveis são importadas.

    converter_numericas : bool, padrão True
        Converte para tipo numérico as variáveis definidas
        como numéricas no input SAS.

    filtrar_entrevistas : bool, padrão True
        Mantém somente registros em que V0015 == "01".

    Retorno
    -------
    pandas.DataFrame
        Base da PNS importada.
    """

    caminho_microdados = Path(caminho_microdados)

    if not caminho_microdados.exists():
        raise FileNotFoundError(
            f"Arquivo dos microdados não encontrado: {caminho_microdados}"
        )

    layout_completo = extrair_layout_pns(caminho_input)

    variaveis_solicitadas = None

    if variaveis is None:
        layout_leitura = layout_completo.copy()

    else:
        if isinstance(variaveis, str):
            variaveis = [variaveis]

        variaveis_solicitadas = list(dict.fromkeys(variaveis))

        disponiveis = set(layout_completo["variavel"])

        ausentes = [
            variavel
            for variavel in variaveis_solicitadas
            if variavel not in disponiveis
        ]

        if ausentes:
            raise ValueError(
                "Variáveis não encontradas no layout: "
                + ", ".join(ausentes)
            )

        variaveis_leitura = variaveis_solicitadas.copy()

        if filtrar_entrevistas and "V0015" not in variaveis_leitura:
            variaveis_leitura.append("V0015")

        layout_leitura = layout_completo[
            layout_completo["variavel"].isin(variaveis_leitura)
        ].copy()

        layout_leitura = (
            layout_leitura
            .sort_values("inicio_sas")
            .reset_index(drop=True)
        )

    colspecs = list(
        zip(
            layout_leitura["inicio_python"],
            layout_leitura["fim_python"],
        )
    )

    nomes = layout_leitura["variavel"].tolist()

    base = pd.read_fwf(
        caminho_microdados,
        colspecs=colspecs,
        names=nomes,
        dtype="string",
        encoding="latin-1",
        keep_default_na=False,
    )

    for coluna in base.columns:
        base[coluna] = base[coluna].str.strip()
        base[coluna] = base[coluna].replace("", pd.NA)

    if filtrar_entrevistas and "V0015" in base.columns:
        base = base.loc[
            base["V0015"].eq("01")
        ].copy()

    if converter_numericas:
        layout_numerico = layout_leitura[
            layout_leitura["tipo_sas"].eq("numerico")
        ]

        for _, especificacao in layout_numerico.iterrows():
            coluna = especificacao["variavel"]

            if coluna not in base.columns:
                continue

            base[coluna] = pd.to_numeric(
                base[coluna],
                errors="coerce",
            )

    if variaveis_solicitadas is not None:
        base = base[variaveis_solicitadas]

    return base.reset_index(drop=True)
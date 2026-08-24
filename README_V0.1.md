# RFT Rolling 12 — V0.1

Dashboard em Streamlit para upload de CSV, cálculo do RFT mensal e cálculo ponderado do Rolling 12.

## Arquivos

- `app_V0.1.py`: aplicação principal.
- `requirements_V0.1.txt`: dependências.
- `CSV_MODELO_V0.1.csv`: exemplo de estrutura por unidade.

## Publicação no GitHub e Streamlit Community Cloud

1. Crie um repositório no GitHub.
2. Envie os três arquivos separadamente.
3. No Streamlit Community Cloud, selecione o repositório e informe `app_V0.1.py` como arquivo principal.
4. Em configurações avançadas, se necessário, aponte as dependências para `requirements_V0.1.txt` ou renomeie esse arquivo para `requirements.txt` no repositório.

## Lógica

- O usuário anexa o CSV.
- O sistema detecta separador e codificação.
- As colunas podem ser mapeadas manualmente.
- A janela usa o mês mais recente do arquivo e os 11 meses anteriores.
- O RFT Rolling 12 é ponderado pelo volume.
- Os códigos de modelo são convertidos para VTBA, V2 MF, V2 VT, G7 e G8.

## Observação importante

A regra de "primeira passagem" depende da estrutura do CSV. Nesta versão, em arquivos por unidade, o primeiro registro cronológico de cada unidade em cada mês define o resultado de primeira passagem. Caso o site de RFT atual use outra regra ou colunas específicas, ajuste a função `calculate_unit_level` após validar um CSV real.

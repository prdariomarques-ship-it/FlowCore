# FlowCore

```bash
git clone https://github.com/prdariomarques-ship-it/FlowCore.git
cd FlowCore
./install.sh
python3 flowcore.py version
```


## Testes

Instale as dependências de desenvolvimento e execute a suíte determinística:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

O teste que consulta cotações externas está marcado como `live` e fica fora da suíte padrão para evitar falhas por indisponibilidade de rede ou do provedor de mercado. Para executá-lo explicitamente:

```bash
python3 -m pytest -q -m live
```

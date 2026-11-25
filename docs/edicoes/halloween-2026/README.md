# Halloween em São Paulo · 31 de outubro de 2026

Baixe [radar-sabado-31-10.html](radar-sabado-31-10.html) e abra o arquivo no navegador. Os filtros funcionam com os dados embutidos na página. A agenda reúne 162 festas, 91 com tema de Halloween e 147 com local divulgado.

A página foi reconstruída com o catálogo e os arquivos de geração da edição publicada em 28 de outubro. O tamanho do HTML e as contagens de eventos, horários e fontes conferem com o registro da entrega. [Edição publicada](https://claude.ai/artifact/SqGwMGM13hraAuMkqbEdjV)

## Como reproduzir

Com Python instalado, rode o comando a partir da raiz do repositório. Ele combina o [JSON da edição](sat_events.json) com o [template](radar_template.html) e recria o HTML.

```sh
python docs/edicoes/halloween-2026/build_page.py
```

Para fazer uma nova extração do período, instale o projeto e configure a conexão com um banco NightLife populado. O script [export_sat.py](export_sat.py) consulta eventos entre 8h de sábado e 6h de domingo, no horário de São Paulo, e substitui o JSON pelo resultado dessa consulta.

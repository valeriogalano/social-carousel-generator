# social-carousel-generator

Script Python per generare un carousel: legge i testi da un file Markdown e li incolla sulle immagini in una cartella `slides`, salvando i risultati in una cartella `output`.

## Requisiti

- Python 3.9+
- Pillow (installabile via pip)

### Uso con ambiente virtuale (venv) consigliato

Per isolare le dipendenze, crea e attiva un ambiente virtuale (venv) nella cartella del progetto.

macOS / Linux:

```shell
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```shell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Windows (CMD):

```shell
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

Per uscire dall'ambiente virtuale:

```shell
deactivate
```

## Struttura attesa

```
assets/
  slides/
    1.png
    2.png
    3.png
  texts.md
```

Il file `texts.md` deve contenere sezioni con titoli di livello 1 che identificano il numero della slide, ad esempio:

```
# 1
Testo per la slide 1 (può essere su più righe)

# 2
Secondo testo
```

Il testo compreso tra `# <numero>` e il successivo titolo è associato a quella slide. Le righe vuote sono permesse.

## Utilizzo

Esempio base:

```bash
python generate_carousel.py \
  --slides-dir assets/slides \
  --texts-file assets/texts.md \
  --output-dir output
```

Opzioni utili:

- `--font-file` path a un font `.ttf`/`.otf` personalizzato
- `--color` colore del testo (default `#ffffff`)
- `--highlight-color` colore delle parti evidenziate con il markup `[[...]]` (default `#37b34a`)
- `--stroke-color` colore del contorno (default `#000000`)
- `--stroke-width` spessore contorno (default `2`)
- `--margin` margine interno in px (default `60`)
- `--max-font-size` dimensione massima font (default `96`)
- `--min-font-size` dimensione minima font (default `24`)
- `--valign` allineamento verticale del blocco testo: `top|center|bottom` (default `center`)
- `--align` allineamento orizzontale delle righe: `left|center` (default `center`)

Il programma abbina i testi alle immagini in base al numero presente nel nome del file della slide (es. `1.png` → sezione `# 1`).

- Se esiste la sezione `# <numero>` ma il testo è vuoto, la slide viene copiata così com'è (senza testo sovrapposto).
- Se non esiste alcuna sezione `# <numero>` corrispondente nel Markdown, la slide viene saltata e non viene generato alcun file di output.
- Se esiste un testo senza immagine corrispondente, verrà segnalato nel riepilogo finale.

I file elaborati vengono salvati nella cartella di output con lo stesso nome dell'immagine sorgente.

## Evidenziare parole o frasi

Puoi ottenere un effetto di evidenziazione come nell'esempio fornito racchiudendo le parole tra doppie parentesi quadre `[[` e `]]` nel file `texts.md`.

Esempio `texts.md`:

```
# 2
Lorem [[ipsum dolor]] sit amet, consectetur [[adipiscing]] elit.
```

Nell'immagine generata, “ipsum dolor” e “adipiscing” saranno disegnate con il colore definito in `--highlight-color` (default verde). Le altre parole useranno `--color`.

Note:
- Non è supportato l'annidamento del markup (`[[ [[ ... ]] ]]`).
- Il wrapping automatico rispetta l'evidenziazione, mantenendo a capo parole intere.
- Per ottenere un layout simile allo screenshot, prova: `--align left --valign top` o `--align left --valign center` a seconda del template.

Esempio di esecuzione con evidenziazione e allineamento a sinistra:

```bash
python generate_carousel.py \
  --slides-dir assets/slides \
  --texts-file assets/texts.md \
  --output-dir output \
  --align left \
  --highlight-color "#37b34a"
```

## Disclaimer

This code was developed as a *vibe coding* experiment. It's important to keep this in mind if you decide to use it in
your projects.

## Licenza

Vedi file `LICENSE`.
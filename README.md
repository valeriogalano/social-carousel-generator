# Social Carousel Generator

> Vibe Coding experiment — progetto costruito con sviluppo iterativo assistito da AI.

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
- `--color` colore del testo normale (default `#ffffff`)
- `--bold-color` colore del testo in grassetto (per `**...**`). Se non impostato, usa `--color`.
- `--italic-color` colore del testo in corsivo (per `*...*`). Se non impostato, usa `--color`.
- `--italic-skew` inclinazione del corsivo in gradi (default `12.0`)
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

## Stili inline: grassetto e corsivo (tipo Markdown minimale)

È possibile controllare lo stile delle parole direttamente nel `texts.md` usando una sintassi in stile Markdown semplificata:

- Grassetto: racchiudi tra `**` → testo disegnato con `--bold-color` (default: `--color`).
- Corsivo: racchiudi tra `*` → testo inclinato (shear) usando `--italic-color` (default: `--color`).

Esempio `texts.md`:

```
# 2
*lorem ipsum dolor* sit amet, consectetur **vestibulum lacinia** elit.
```

Note:
- Il wrapping automatico rispetta gli stili, mantenendo a capo parole intere.
- L'effetto corsivo è ottenuto tramite un'inclinazione (shear) dell'immagine del testo; per un risultato perfetto puoi usare un font italic con `--font-file`.
- Puoi regolare l'inclinazione del corsivo con `--italic-skew` (gradi).
- Non è più supportato l'highlight `[[...]]` né il contorno/stroke del testo.

Esempio di esecuzione con grassetto verde, corsivo arancione e allineamento a sinistra:

```bash
python generate_carousel.py \
  --slides-dir assets/slides \
  --texts-file assets/texts.md \
  --output-dir output \
  --align left \
  --bold-color "#37b34a" \
  --italic-color "#ff8a00"
```

## Licenza

See the [LICENSE](LICENSE) file for details.

---

<div align="center">
  <p>Realizzato con ❤️ da <strong>Valerio Galano</strong></p>
  <p>
    <a href="https://valeriogalano.it/">Sito Web</a> |
    <a href="https://daredevel.com/">Blog</a> |
    <a href="https://pensieriincodice.it/">Podcast</a>
  </p>
</div>

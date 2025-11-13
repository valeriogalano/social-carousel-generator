#!/usr/bin/env python3
"""
Generatore di carousel: legge testi da un file Markdown e li incolla sulle immagini
rispettando la numerazione dei file slide.

Uso base:
  python generate_carousel.py \
      --slides-dir assets/slides \
      --texts-file assets/texts.md \
      --output-dir output

Opzioni aggiuntive: --font-file, --color, --highlight-color, --stroke-color, --stroke-width, --margin, --position

Formato atteso del file testi (Markdown):
  # 1
  Primo testo della slide 1

  # 2
  Testo slide 2 su una o più righe

Tutto il testo fino al prossimo titolo di livello 1 ("# <numero>") viene associato a quella slide.

Nota sul comportamento:
- Se esiste la sezione numerata nel Markdown ma il testo è vuoto, la slide viene COPIATA così com'è nell'output.
- Se NON esiste una sezione numerata corrispondente nel Markdown, la slide viene SALTATA (non viene generato alcun file).

Evidenziazione (inline highlight):
- Puoi evidenziare parole o sequenze di parole racchiudendole tra [[ e ]]. Esempio:
  "Lorem [[ipsum dolor]] sit amet" → le parole "ipsum dolor" verranno colorate con
  il colore impostato in --highlight-color (default verde).
  Non è supportato l'annidamento.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Iterable

from PIL import Image, ImageDraw, ImageFont


TITLE_RE = re.compile(r"^#\s*(\d+)\s*$")


def parse_texts_md(path: Path) -> Dict[int, str]:
    """Parsa un file Markdown in sezioni numerate con pattern "# <n>".
    Ritorna un dizionario {numero_slide: testo}.
    """
    sections: Dict[int, List[str]] = {}
    current: int | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = TITLE_RE.match(raw.strip())
        if m:
            current = int(m.group(1))
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(raw.rstrip())
    # join and normalize whitespace (preserva righe vuote come nuove linee)
    joined: Dict[int, str] = {}
    for k, lines in sections.items():
        # rimuovi righe vuote alle estremità
        while lines and lines[0].strip() == "":
            lines.pop(0)
        while lines and lines[-1].strip() == "":
            lines.pop()
        joined[k] = "\n".join(lines).strip()
    return joined


def find_images(slides_dir: Path) -> List[Path]:
    """Trova immagini supportate nella cartella slides, ordinate per numero estratto dal nome file.
    Supporta estensioni: .png .jpg .jpeg .webp
    Nomina attesa: "<numero>.<ext>" oppure con prefissi/testi, purché contenga un intero.
    """
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    files = [p for p in slides_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]

    def extract_index(p: Path) -> Tuple[int, str]:
        # cerca il primo intero nel nome file
        m = re.search(r"(\d+)", p.stem)
        idx = int(m.group(1)) if m else 10**9
        return idx, p.name

    files.sort(key=extract_index)
    return files


@dataclass
class RenderConfig:
    font_file: str | None
    color: str
    highlight_color: str
    stroke_color: str
    stroke_width: int
    margin: int
    max_font_size: int
    min_font_size: int
    valign: str  # top, center, bottom
    align: str  # left, center


def load_font(cfg: RenderConfig, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Prova truetype indicato; in alternativa tenta DejaVuSans; fallback a default bitmap
    if cfg.font_file:
        try:
            return ImageFont.truetype(cfg.font_file, size=size)
        except Exception:
            pass
    for candidate in ("DejaVuSans.ttf", "Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _parse_tokens_line(line: str) -> List[Tuple[str, bool]]:
    """Parsa una riga con markup [[...]] restituendo tokens (word, is_highlight).
    Lo spazio tra le parole è gestito in fase di wrapping, quindi ogni token è una
    singola parola (con punteggiatura).
    """
    tokens: List[Tuple[str, bool]] = []
    i = 0
    in_h = False
    buf = []
    while i < len(line):
        if line.startswith("[[", i) and not in_h:
            # flush buffer normale
            if buf:
                for w in "".join(buf).split():
                    if w:
                        tokens.append((w, False))
                buf = []
            in_h = True
            i += 2
            continue
        if line.startswith("]]", i) and in_h:
            if buf:
                for w in "".join(buf).split():
                    if w:
                        tokens.append((w, True))
                buf = []
            in_h = False
            i += 2
            continue
        buf.append(line[i])
        i += 1
    if buf:
        for w in "".join(buf).split():
            if w:
                tokens.append((w, in_h))
    return tokens


def _tokenize_text(text: str) -> List[List[Tuple[str, bool]]]:
    """Converte il testo in una lista di paragrafi; ogni paragrafo è lista di tokens.
    Le righe vuote generano paragrafi vuoti (linea vuota nell'output).
    """
    paragraphs: List[List[Tuple[str, bool]]] = []
    for raw in text.split("\n"):
        if raw.strip() == "":
            paragraphs.append([])  # linea vuota
        else:
            paragraphs.append(_parse_tokens_line(raw))
    return paragraphs


def _wrap_rich_tokens(draw: ImageDraw.ImageDraw, tokens: Iterable[Tuple[str, bool]], font: ImageFont.ImageFont, max_width: int) -> List[List[Tuple[str, bool]]]:
    """Esegue il wrapping di una sequenza di token in righe (liste di token)."""
    lines: List[List[Tuple[str, bool]]] = []
    line: List[Tuple[str, bool]] = []
    width = 0.0
    space_w = draw.textlength(" ", font=font)
    for word, is_h in tokens:
        add_w = draw.textlength(word, font=font) + (space_w if line else 0.0)
        if line and width + add_w > max_width:
            lines.append(line)
            line = [(word, is_h)]
            width = draw.textlength(word, font=font)
        else:
            if line:
                width += space_w
            width += draw.textlength(word, font=font)
            line.append((word, is_h))
    if line or not lines:
        lines.append(line)
    return lines


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[List[Tuple[str, bool]]]:
    """Effettua wrapping conservando i token evidenziati. Ritorna lista di righe."""
    paragraphs = _tokenize_text(text)
    all_lines: List[List[Tuple[str, bool]]] = []
    for para in paragraphs:
        if not para:  # linea vuota
            all_lines.append([])
            continue
        lines = _wrap_rich_tokens(draw, para, font, max_width)
        all_lines.extend(lines)
    return all_lines


def fit_text_in_box(draw: ImageDraw.ImageDraw, text: str, cfg: RenderConfig, box_w: int, box_h: int) -> Tuple[ImageFont.ImageFont, List[List[Tuple[str, bool]]]]:
    """Riduce la dimensione del font finché il testo wrappato entra nel box.
    Restituisce (font, righe_token).
    """
    size = cfg.max_font_size
    while size >= cfg.min_font_size:
        font = load_font(cfg, size)
        wrapped_lines = wrap_text(draw, text, font, max_width=box_w)
        # misura blocco
        ascent, descent = getattr(font, "getmetrics", lambda: (size, int(size*0.25)))()
        line_h = ascent + descent
        spacing = int(size * 0.25)
        non_empty = [ln for ln in wrapped_lines]
        # calcolo altezza: ogni linea (anche vuota) occupa line_h, tra linee aggiungi spacing
        h = len(non_empty) * line_h + max(0, len(non_empty) - 1) * spacing
        # stima larghezza massima della linea
        max_w = 0
        for ln in wrapped_lines:
            text_line = " ".join([t for t, _ in ln])
            max_w = max(max_w, int(draw.textlength(text_line, font=font)))
        w = max_w
        if w <= box_w and h <= box_h:
            return font, wrapped_lines
        size = max(cfg.min_font_size, size - 2)
        if size == cfg.min_font_size:
            # prova ultima volta
            font = load_font(cfg, size)
            wrapped_lines = wrap_text(draw, text, font, max_width=box_w)
            ascent, descent = getattr(font, "getmetrics", lambda: (size, int(size*0.25)))()
            line_h = ascent + descent
            spacing = int(size * 0.25)
            h = len(wrapped_lines) * line_h + max(0, len(wrapped_lines) - 1) * spacing
            max_w = 0
            for ln in wrapped_lines:
                text_line = " ".join([t for t, _ in ln])
                max_w = max(max_w, int(draw.textlength(text_line, font=font)))
            w = max_w
            if w <= box_w and h <= box_h:
                return font, wrapped_lines
            break
    f = load_font(cfg, cfg.min_font_size)
    return f, wrap_text(draw, text, f, max_width=box_w)


def render_on_image(img_path: Path, text: str, out_path: Path, cfg: RenderConfig) -> None:
    im = Image.open(img_path).convert("RGBA")
    W, H = im.size
    draw = ImageDraw.Draw(im)

    margin = cfg.margin
    box_w = W - 2 * margin
    box_h = H - 2 * margin

    font, lines = fit_text_in_box(draw, text, cfg, box_w, box_h)
    spacing = int(font.size * 0.25)
    ascent, descent = getattr(font, "getmetrics", lambda: (font.size, int(font.size*0.25)))()
    line_h = ascent + descent

    # calcolo altezza totale
    th = len(lines) * line_h + max(0, len(lines) - 1) * spacing

    # x base per allineamento a sinistra
    left_x = margin

    if cfg.valign == "top":
        y = margin
    elif cfg.valign == "bottom":
        y = H - margin - th
    else:
        y = (H - th) // 2

    # Disegna riga per riga, token per token (colorando le parti evidenziate)
    space_w = draw.textlength(" ", font=font)
    for line_tokens in lines:
        # Larghezza effettiva della riga (stringa unita con spazi)
        line_text = " ".join([t for t, _ in line_tokens])
        line_w = int(draw.textlength(line_text, font=font))
        if cfg.align == "center":
            x = (W - line_w) // 2
        else:
            x = left_x

        # Disegna i token
        for idx, (tok, is_h) in enumerate(line_tokens):
            fill_color = cfg.highlight_color if is_h else cfg.color
            draw.text(
                (x, y),
                tok,
                font=font,
                fill=fill_color,
                stroke_width=cfg.stroke_width,
                stroke_fill=cfg.stroke_color,
            )
            x += int(draw.textlength(tok, font=font))
            if idx != len(line_tokens) - 1:
                x += int(space_w)
        y += line_h + spacing

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # salva come PNG per preservare qualità/testo; mantiene estensione originale se non PNG
    im = im.convert("RGB") if out_path.suffix.lower() in {".jpg", ".jpeg"} else im
    im.save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Incolla testi su immagini in base alla numerazione")
    parser.add_argument("--slides-dir", required=True, type=Path, help="Cartella con le immagini delle slide")
    parser.add_argument("--texts-file", required=True, type=Path, help="File Markdown con i testi (sezioni '# <n>')")
    parser.add_argument("--output-dir", required=True, type=Path, help="Cartella di destinazione")
    parser.add_argument("--font-file", type=str, default=None, help="Path ad un font .ttf/.otf personalizzato")
    parser.add_argument("--color", type=str, default="#ffffff", help="Colore del testo (hex o nome)")
    parser.add_argument("--highlight-color", type=str, default="#37b34a", help="Colore delle parti evidenziate ([[...]]))")
    parser.add_argument("--stroke-color", type=str, default="#000000", help="Colore contorno testo")
    parser.add_argument("--stroke-width", type=int, default=2, help="Spessore contorno testo")
    parser.add_argument("--margin", type=int, default=60, help="Margine interno (px)")
    parser.add_argument("--max-font-size", type=int, default=96, help="Dimensione massima font")
    parser.add_argument("--min-font-size", type=int, default=24, help="Dimensione minima font")
    parser.add_argument("--valign", choices=["top", "center", "bottom"], default="center", help="Allineamento verticale del blocco testo")
    parser.add_argument("--align", choices=["left", "center"], default="center", help="Allineamento orizzontale delle righe")

    args = parser.parse_args()

    slides_dir: Path = args.slides_dir
    texts_file: Path = args.texts_file
    output_dir: Path = args.output_dir

    if not slides_dir.exists() or not slides_dir.is_dir():
        parser.error(f"Cartella slides non valida: {slides_dir}")
    if not texts_file.exists() or not texts_file.is_file():
        parser.error(f"File testi non valido: {texts_file}")

    texts = parse_texts_md(texts_file)
    images = find_images(slides_dir)

    cfg = RenderConfig(
        font_file=args.font_file,
        color=args.color,
        highlight_color=args.highlight_color,
        stroke_color=args.stroke_color,
        stroke_width=int(args.stroke_width),
        margin=int(args.margin),
        max_font_size=int(args.max_font_size),
        min_font_size=int(args.min_font_size),
        valign=args.valign,
        align=args.align,
    )

    # mappa numero -> path immagine (ultimo vince se duplicati)
    num_to_img: Dict[int, Path] = {}
    for p in images:
        m = re.search(r"(\d+)", p.stem)
        if not m:
            continue
        num_to_img[int(m.group(1))] = p

    processed = 0
    skipped = 0  # testi senza immagine
    copied_empty = 0  # slide con sezione numerata ma testo vuoto
    skipped_no_number = 0  # slide senza sezione numerata corrispondente

    # processa tutte le immagini trovate
    for num, img_path in sorted(num_to_img.items(), key=lambda kv: kv[0]):
        out_path = output_dir / img_path.name
        if num in texts:
            if texts[num].strip():
                render_on_image(img_path, texts[num], out_path, cfg)
                processed += 1
            else:
                # se la sezione esiste ma non ha testo, copia l'immagine originale
                out_path.parent.mkdir(parents=True, exist_ok=True)
                Image.open(img_path).save(out_path)
                copied_empty += 1
        else:
            # non esiste sezione numerata corrispondente nel markdown: salta
            skipped_no_number += 1

    # warning per testi senza immagine
    for tnum in sorted(texts.keys()):
        if tnum not in num_to_img:
            skipped += 1

    print(
        f"Slides elaborate: {processed}, copiate senza testo: {copied_empty}, "
        f"saltate senza numero: {skipped_no_number}, testi senza immagine: {skipped}"
    )
    print(f"Output salvato in: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

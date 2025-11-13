#!/usr/bin/env python3
"""
Generatore di carousel: legge testi da un file Markdown e li incolla sulle immagini
rispettando la numerazione dei file slide.

Uso base:
  python generate_carousel.py \
      --slides-dir assets/slides \
      --texts-file assets/texts.md \
      --output-dir output

Opzioni aggiuntive: --font-file, --color, --stroke-color, --stroke-width, --margin, --position

Formato atteso del file testi (Markdown):
  # 1
  Primo testo della slide 1

  # 2
  Testo slide 2 su una o più righe

Tutto il testo fino al prossimo titolo di livello 1 ("# <numero>") viene associato a quella slide.

Nota sul comportamento:
- Se esiste la sezione numerata nel Markdown ma il testo è vuoto, la slide viene COPIATA così com'è nell'output.
- Se NON esiste una sezione numerata corrispondente nel Markdown, la slide viene SALTATA (non viene generato alcun file).
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

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
    stroke_color: str
    stroke_width: int
    margin: int
    max_font_size: int
    min_font_size: int
    valign: str  # top, center, bottom


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


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    lines_out: List[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines_out.append("")
            continue
        line = words[0]
        for w in words[1:]:
            test = f"{line} {w}"
            wpx = draw.textlength(test, font=font)
            if wpx <= max_width:
                line = test
            else:
                lines_out.append(line)
                line = w
        lines_out.append(line)
    return "\n".join(lines_out)


def fit_text_in_box(draw: ImageDraw.ImageDraw, text: str, cfg: RenderConfig, box_w: int, box_h: int) -> Tuple[ImageFont.ImageFont, str]:
    """Riduce la dimensione del font finché il testo wrappato entra nel box."""
    size = cfg.max_font_size
    while size >= cfg.min_font_size:
        font = load_font(cfg, size)
        wrapped = wrap_text(draw, text, font, max_width=box_w)
        # misura altezza
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=int(size*0.25), stroke_width=cfg.stroke_width)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w <= box_w and h <= box_h:
            return font, wrapped
        size = max(cfg.min_font_size, size - 2)
        if size == cfg.min_font_size:
            # prova ultima volta
            font = load_font(cfg, size)
            wrapped = wrap_text(draw, text, font, max_width=box_w)
            bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=int(size*0.25), stroke_width=cfg.stroke_width)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            if w <= box_w and h <= box_h:
                return font, wrapped
            break
    return load_font(cfg, cfg.min_font_size), wrap_text(draw, text, load_font(cfg, cfg.min_font_size), max_width=box_w)


def render_on_image(img_path: Path, text: str, out_path: Path, cfg: RenderConfig) -> None:
    im = Image.open(img_path).convert("RGBA")
    W, H = im.size
    draw = ImageDraw.Draw(im)

    margin = cfg.margin
    box_w = W - 2 * margin
    box_h = H - 2 * margin

    font, wrapped = fit_text_in_box(draw, text, cfg, box_w, box_h)
    spacing = int(font.size * 0.25)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=spacing, stroke_width=cfg.stroke_width)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    x = (W - tw) // 2
    if cfg.valign == "top":
        y = margin
    elif cfg.valign == "bottom":
        y = H - margin - th
    else:
        y = (H - th) // 2

    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=cfg.color,
        align="center",
        spacing=spacing,
        stroke_width=cfg.stroke_width,
        stroke_fill=cfg.stroke_color,
        anchor=None,
    )

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
    parser.add_argument("--stroke-color", type=str, default="#000000", help="Colore contorno testo")
    parser.add_argument("--stroke-width", type=int, default=2, help="Spessore contorno testo")
    parser.add_argument("--margin", type=int, default=60, help="Margine interno (px)")
    parser.add_argument("--max-font-size", type=int, default=96, help="Dimensione massima font")
    parser.add_argument("--min-font-size", type=int, default=24, help="Dimensione minima font")
    parser.add_argument("--valign", choices=["top", "center", "bottom"], default="center", help="Allineamento verticale del blocco testo")

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
        stroke_color=args.stroke_color,
        stroke_width=int(args.stroke_width),
        margin=int(args.margin),
        max_font_size=int(args.max_font_size),
        min_font_size=int(args.min_font_size),
        valign=args.valign,
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
